"""
Synthetic Data Generator cho DRL Autoscaling - apigateway service
Dựa trên hệ số học từ 241 dòng data thực tế

Các quy luật đã học được:
  CPU:     cpu = 0.10221 * rps / replicas - 0.65666/replicas  (R²=0.818)
           noise ~ N(0, 0.82²)
  Memory:  mem = 28.54 + 0.24*replicas - 0.057*rps           (R²=0.611)
  Latency: 2 regime:
           - Normal (rps < 130): base 4.2ms + 0.02*rps_per_pod + noise
           - Spike  (rps >= 130 và replicas <= 3): 30–200ms
           (Dùng RPS threshold vì corr(latency,rps)=0.365 > corr(latency,cpu)=0.134
            trong data thực — CPU không phải predictor tốt nhất cho hệ thống này)
  HPA:     scale up  nếu cpu_avg_2_bước > 3.58
           scale down nếu cpu_avg_2_bước < 1.69
           min=1, max=6 replicas
  Lag:     pod startup ~20–30s = 2 timestep (15s/step)
           → replicas thực tế apply sau 2 bước, trong thời gian chờ
             CPU/latency tính theo replicas cũ (warmup effect)
  Jitter:  CPU có autocorrelated noise (AR(1), phi=0.4) thay vì i.i.d
           Latency có occasional burst noise độc lập với regime
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

# =================== THAM SỐ HỌC TỪ DATA THỰC ===================
# CPU model: cpu_total = coef * rps + intercept  (rồi chia replicas)
CPU_COEF_RPS        = 0.10221   # hệ số rps → cpu*replicas
CPU_INTERCEPT       = -0.65666
CPU_NOISE_STD       = 0.82      # std của residuals

# Memory model
MEM_BASE            = 28.54
MEM_COEF_REPLICAS   = 0.24
MEM_COEF_RPS        = -0.057
MEM_NOISE_STD       = 1.2

# Latency model
LAT_NORMAL_BASE     = 4.2       # ms khi hệ thống ổn định (calibrated: median=4.78 vs real=4.81)
LAT_NORMAL_NOISE    = 0.8
LAT_SPIKE_THRESHOLD_RPS      = 130   # rps vượt mức này bắt đầu risk spike
LAT_SPIKE_THRESHOLD_REPLICAS = 3     # nếu replicas <= này + rps cao → spike
LAT_SPIKE_MEAN      = 67.0
LAT_SPIKE_STD       = 52.0
# Occasional burst noise: ~2% rows có latency jitter bất thường dù không spike
LAT_BURST_PROB      = 0.02
LAT_BURST_MEAN      = 18.0
LAT_BURST_STD       = 8.0

# HPA threshold (học từ data thực)
HPA_SCALE_UP_CPU    = 3.58      # CPU mean 2 bước > này → scale up
HPA_SCALE_DOWN_CPU  = 1.69      # CPU mean 2 bước < này → scale down
HPA_MIN_REPLICAS    = 1
HPA_MAX_REPLICAS    = 6
HPA_COOLDOWN_STEPS  = 4         # bước cooldown sau mỗi lần scale (~60s)

# Scaling transition lag (pod startup ~20-30s = 2 timestep với step=15s)
# Trong thời gian chờ pod ready, hệ thống vẫn dùng replicas cũ → CPU/latency cao hơn
POD_STARTUP_STEPS   = 2         # số timestep để pod mới ready

# Jitter: CPU noise có tương quan thời gian (AR(1)) thay vì i.i.d
# Học từ data thực: CPU không nhảy ngẫu nhiên mà drift dần
CPU_AR1_PHI         = 0.4       # hệ số autocorrelation (0=i.i.d, 1=random walk)

# =================== WORKLOAD PATTERNS ===================
def generate_rps_pattern(pattern: str, n_steps: int) -> np.ndarray:
    """
    Sinh chuỗi RPS theo các kịch bản khác nhau
    Dựa trên statistics thực tế:
      ramp_up:     mean=58.76, std=5.14
      steady:      mean=59.82, std=0.29
      multi_spike: mean=105.55, std=42.39  (peak=150)
      long_wave:   mean=79.29, std=32.57   (sin wave)
      cooldown:    mean=10.65, std=2.29
    """
    t = np.arange(n_steps)

    if pattern == "steady":
        base = np.full(n_steps, 60.0)
        noise = np.random.normal(0, 0.3, n_steps)
        return np.clip(base + noise, 5, 80)

    elif pattern == "ramp_up":
        rps = np.linspace(5, 65, n_steps)
        noise = np.random.normal(0, 3, n_steps)
        return np.clip(rps + noise, 5, 80)

    elif pattern == "ramp_down":
        rps = np.linspace(65, 5, n_steps)
        noise = np.random.normal(0, 3, n_steps)
        return np.clip(rps + noise, 5, 80)

    elif pattern == "spike":
        # Tải bình thường rồi đột ngột tăng lên ~150 rồi giảm
        base = np.full(n_steps, 60.0)
        spike_start = n_steps // 3
        spike_end   = 2 * n_steps // 3
        base[spike_start:spike_end] = 145
        noise = np.random.normal(0, 5, n_steps)
        return np.clip(base + noise, 5, 160)

    elif pattern == "multi_spike":
        # Nhiều đợt spike xen kẽ (khớp với phase multi_spike của Locust)
        base = np.full(n_steps, 60.0)
        period = n_steps // 4
        for i in range(4):
            if i % 2 == 0:
                s = i * period
                e = min(s + period, n_steps)
                base[s:e] = 145
        noise = np.random.normal(0, 8, n_steps)
        return np.clip(base + noise, 5, 160)

    elif pattern == "sine_wave":
        # Sóng sin biên độ lớn (long_wave phase): mean=79, amplitude~50
        amplitude = 50
        mean_rps   = 80
        period_steps = max(1, n_steps // 3)
        rps = mean_rps + amplitude * np.sin(2 * np.pi * t / period_steps)
        noise = np.random.normal(0, 5, n_steps)
        return np.clip(rps + noise, 5, 160)

    elif pattern == "realistic_60min":
        # Mô phỏng lại đúng kịch bản Locust 60 phút
        # ramp_up(10p) → steady(15p) → multi_spike(10p) → sine_wave(15p) → cooldown(10p)
        total = n_steps
        p = [int(total*10/60), int(total*25/60), int(total*35/60),
             int(total*50/60), total]
        rps = np.zeros(total)
        rps[:p[0]]      = generate_rps_pattern("ramp_up",   p[0])
        rps[p[0]:p[1]]  = generate_rps_pattern("steady",    p[1]-p[0])
        rps[p[1]:p[2]]  = generate_rps_pattern("multi_spike", p[2]-p[1])
        rps[p[2]:p[3]]  = generate_rps_pattern("sine_wave", p[3]-p[2])
        rps[p[3]:]      = generate_rps_pattern("ramp_down", total-p[3])
        return rps

    else:
        raise ValueError(f"Unknown pattern: {pattern}")


# =================== SIMULATOR ===================
def simulate_service(rps_series: np.ndarray, start_replicas: int = 1) -> pd.DataFrame:
    """
    Mô phỏng hành vi apigateway theo từng timestep 15s
    Có 2 cải tiến so với version gốc:
      1. Scaling transition lag: pod mới mất POD_STARTUP_STEPS bước để ready
         → trong thời gian chờ, CPU/latency tính theo replicas cũ (effective_replicas)
      2. Jitter thực tế:
         - CPU noise dùng AR(1) thay vì i.i.d (drift dần như hệ thật)
         - Latency có occasional burst noise (2% rows) độc lập với spike regime
    """
    n = len(rps_series)
    records = []

    replicas          = start_replicas   # replicas đã apply (pod ready)
    pending_replicas  = start_replicas   # replicas đã được ra lệnh nhưng chưa ready
    startup_countdown = 0                # còn bao nhiêu bước nữa pod mới ready
    cooldown_left     = 0
    cpu_history       = []              # lưu 2 bước để tính avg như HPA thật
    cpu_ar1_noise     = 0.0             # AR(1) noise state cho CPU jitter

    for i in range(n):
        rps = rps_series[i]

        # --- [MỚI] Xử lý scaling lag ---
        # effective_replicas = số pod thực sự đang phục vụ request
        # Nếu đang trong startup countdown → pod mới chưa ready → dùng replicas cũ
        if startup_countdown > 0:
            effective_replicas = replicas          # pod cũ vẫn chịu tải
            startup_countdown -= 1
            if startup_countdown == 0:
                replicas = pending_replicas        # pod mới ready, apply chính thức
        else:
            effective_replicas = replicas

        # --- Tính CPU (dùng effective_replicas) ---
        cpu_total  = CPU_COEF_RPS * rps + CPU_INTERCEPT
        cpu_base   = cpu_total / effective_replicas
        # [MỚI] AR(1) noise: noise_t = phi * noise_{t-1} + epsilon
        # Tạo cảm giác CPU drift lên/xuống dần thay vì nhảy ngẫu nhiên
        epsilon        = np.random.normal(0, CPU_NOISE_STD * np.sqrt(1 - CPU_AR1_PHI**2))
        cpu_ar1_noise  = CPU_AR1_PHI * cpu_ar1_noise + epsilon
        cpu            = max(0.1, cpu_base + cpu_ar1_noise)

        # --- Tính Memory (ít bị ảnh hưởng bởi lag, dùng pending_replicas) ---
        mem = MEM_BASE + MEM_COEF_REPLICAS * pending_replicas + MEM_COEF_RPS * rps
        mem += np.random.normal(0, MEM_NOISE_STD)
        mem  = np.clip(mem, 10, 40)

        # --- Tính Latency (dùng effective_replicas, RPS threshold từ data thực) ---
        # corr(latency, rps)=0.365 > corr(latency, cpu)=0.134 → giữ RPS threshold
        is_spike_condition = (rps >= LAT_SPIKE_THRESHOLD_RPS and
                              effective_replicas <= LAT_SPIKE_THRESHOLD_REPLICAS)
        if is_spike_condition:
            lat = abs(np.random.normal(LAT_SPIKE_MEAN, LAT_SPIKE_STD))
            lat = np.clip(lat, 15, 200)
        else:
            rps_per_pod = rps / effective_replicas
            lat_base    = LAT_NORMAL_BASE + 0.02 * rps_per_pod
            lat         = lat_base + np.random.normal(0, LAT_NORMAL_NOISE)
            lat         = max(1.0, lat)

        # [MỚI] Occasional burst noise: ~2% rows có jitter bất thường
        # Mô phỏng GC pause, network hiccup, cold start nhỏ
        if np.random.random() < LAT_BURST_PROB:
            lat += abs(np.random.normal(LAT_BURST_MEAN, LAT_BURST_STD))

        # --- HPA Decision ---
        cpu_history.append(cpu)
        if len(cpu_history) > 2:
            cpu_history.pop(0)

        observed_replicas = replicas     # HPA thấy replicas đã apply, không thấy pending
        action            = 0            # 0=stay, 1=scale_up, -1=scale_down

        if cooldown_left > 0:
            cooldown_left -= 1
        elif len(cpu_history) == 2 and startup_countdown == 0:
            # HPA chỉ ra quyết định khi không có pod đang khởi động
            cpu_avg = np.mean(cpu_history)
            if cpu_avg > HPA_SCALE_UP_CPU and pending_replicas < HPA_MAX_REPLICAS:
                pending_replicas  += 1
                action             = 1
                startup_countdown  = POD_STARTUP_STEPS   # pod mới cần 2 bước để ready
                cooldown_left      = HPA_COOLDOWN_STEPS
            elif cpu_avg < HPA_SCALE_DOWN_CPU and pending_replicas > HPA_MIN_REPLICAS:
                # Scale down apply ngay (không cần warmup)
                pending_replicas -= 1
                replicas          = pending_replicas
                action            = -1
                cooldown_left     = HPA_COOLDOWN_STEPS

        records.append({
            "step":               i,
            "rps":                round(rps, 4),
            "cpu":                round(cpu, 4),
            "memory":             round(mem, 4),
            "latency_p95":        round(lat, 4),
            "replicas":           observed_replicas,    # replicas HPA thấy (đã apply)
            "effective_replicas": effective_replicas,   # replicas thực tế đang chịu tải
            "pending_replicas":   pending_replicas,     # replicas đã ra lệnh (kể cả đang khởi động)
            "next_replicas":      replicas,             # replicas sau bước này
            "action":             action,               # -1, 0, 1
            "in_startup":         int(startup_countdown > 0),  # 1 nếu đang chờ pod ready
        })

    df = pd.DataFrame(records)

    # Tính thêm các cột hữu ích cho RL
    df["rps_per_pod"]  = (df["rps"] / df["effective_replicas"]).round(4)
    df["sla_violated"] = (df["latency_p95"] > 100).astype(int)  # SLA = 100ms

    # next_state columns (cho offline RL)
    for col in ["rps", "cpu", "memory", "latency_p95"]:
        df[f"next_{col}"] = df[col].shift(-1)
    df.dropna(inplace=True)

    return df


# =================== SINH BỘ DATA LỚN ===================
def generate_dataset(n_episodes: int = 200, steps_per_episode: int = 240,
                     output_path: str = "synthetic_dataset.csv") -> pd.DataFrame:
    """
    Sinh n_episodes episodes, mỗi episode là 1 lần chạy 60 phút (240 steps × 15s)
    Tổng: 200 × 240 = 48,000 transitions
    """
    patterns = ["steady", "spike", "multi_spike", "sine_wave",
                "ramp_up", "ramp_down", "realistic_60min"]

    # Phân bổ episodes theo pattern — tăng ramp_up/ramp_down để phủ vùng RPS thấp
    weights = [0.10, 0.22, 0.22, 0.18, 0.08, 0.10, 0.10]
    #           steady spike  multi  sine  real  ramp↑ ramp↓

    all_dfs = []
    episode_counts = np.random.choice(len(patterns), size=n_episodes, p=weights)

    print(f"Sinh {n_episodes} episodes × {steps_per_episode} steps = "
          f"{n_episodes * steps_per_episode:,} transitions...")

    for ep_idx, pattern_idx in enumerate(episode_counts):
        pattern = patterns[pattern_idx]
        rps = generate_rps_pattern(pattern, steps_per_episode)
        start_rep = np.random.choice([1, 2, 3], p=[0.6, 0.3, 0.1])
        df_ep = simulate_service(rps, start_replicas=start_rep)
        df_ep["episode"]  = ep_idx
        df_ep["pattern"]  = pattern
        all_dfs.append(df_ep)

        if (ep_idx + 1) % 50 == 0:
            print(f"  [{ep_idx+1}/{n_episodes}] done...")

    dataset = pd.concat(all_dfs, ignore_index=True)
    dataset.to_csv(output_path, index=False)

    # Thống kê
    print(f"\n✅ Dataset saved: {output_path}")
    print(f"   Total rows       : {len(dataset):,}")
    print(f"   Action dist      : {dataset['action'].value_counts().sort_index().to_dict()}")
    print(f"   Scale up events  : {(dataset['action']==1).sum():,}")
    print(f"   Scale down       : {(dataset['action']==-1).sum():,}")
    print(f"   SLA violations   : {dataset['sla_violated'].sum():,} "
          f"({dataset['sla_violated'].mean()*100:.1f}%)")
    print(f"   In-startup rows  : {dataset['in_startup'].sum():,} "
          f"({dataset['in_startup'].mean()*100:.1f}%)")
    print(f"   Replicas dist    : {dataset['replicas'].value_counts().sort_index().to_dict()}")
    print(f"\n   CPU  - mean={dataset['cpu'].mean():.2f}, std={dataset['cpu'].std():.2f}, "
          f"max={dataset['cpu'].max():.2f}")
    print(f"   Lat  - mean={dataset['latency_p95'].mean():.2f}, median={dataset['latency_p95'].median():.2f}, "
          f"std={dataset['latency_p95'].std():.2f}, max={dataset['latency_p95'].max():.2f}")

    return dataset


if __name__ == "__main__":
    df = generate_dataset(
        n_episodes=420,
        steps_per_episode=240,
        output_path="synthetic_dataset.csv"
    )
    print("\nSample rows:")
    print(df[["episode","pattern","rps","cpu","memory","latency_p95",
              "replicas","effective_replicas","action","in_startup","sla_violated"]].sample(10).to_string())