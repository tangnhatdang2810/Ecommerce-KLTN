package hipstershop;

import hipstershop.model.Money;

/**
 * Utility class for Money arithmetic operations.
 * Ported from the original Go implementation.
 */
public final class MoneyUtils {

    private static final int NANOS_MOD = 1_000_000_000;
    private static final int NANOS_MAX = 999_999_999;
    private static final int NANOS_MIN = -999_999_999;

    private MoneyUtils() {}

    public static boolean isValid(Money m) {
        return signMatches(m) && validNanos(m.getNanos());
    }

    private static boolean signMatches(Money m) {
        return m.getNanos() == 0 || m.getUnits() == 0 ||
               (m.getNanos() < 0) == (m.getUnits() < 0);
    }

    private static boolean validNanos(int nanos) {
        return NANOS_MIN <= nanos && nanos <= NANOS_MAX;
    }

    public static boolean isZero(Money m) {
        return m.getUnits() == 0 && m.getNanos() == 0;
    }

    /**
     * Sum adds two Money values. Both must have the same currency.
     */
    public static Money sum(Money l, Money r) {
        if (!isValid(l) || !isValid(r)) {
            throw new IllegalArgumentException("One of the specified money values is invalid");
        }
        if (!l.getCurrencyCode().equals(r.getCurrencyCode())) {
            throw new IllegalArgumentException("Mismatching currency codes: " +
                    l.getCurrencyCode() + " vs " + r.getCurrencyCode());
        }

        long units = l.getUnits() + r.getUnits();
        int nanos = l.getNanos() + r.getNanos();

        if ((units == 0 && nanos == 0) || (units > 0 && nanos >= 0) || (units < 0 && nanos <= 0)) {
            // same sign
            units += nanos / NANOS_MOD;
            nanos = nanos % NANOS_MOD;
        } else {
            // different sign
            if (units > 0) {
                units--;
                nanos += NANOS_MOD;
            } else {
                units++;
                nanos -= NANOS_MOD;
            }
        }

        return new Money(l.getCurrencyCode(), units, nanos);
    }

    /**
     * MultiplySlow multiplies a Money value by n using repeated addition.
     */
    public static Money multiplySlow(Money m, int n) {
        Money out = m;
        for (int i = 1; i < n; i++) {
            out = sum(out, m);
        }
        return out;
    }
}
