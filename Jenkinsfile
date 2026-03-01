pipeline {
    agent { label 'agent-1' }

    environment {
        DOCKER_REGISTRY  = "tangnhatdang"
        IMAGE_PREFIX     = "ecommerce-kltn"
        SONAR_HOME       = "/opt/sonar-scanner"

        TRIVY_CACHE_DIR  = "/opt/trivy-cache"
        TMPDIR           = "/opt/tmp"
    }

    stages {

    // =================================================
    // CHECKOUT
    // =================================================
        stage('Checkout') {
            steps {
                git branch: 'main',
                    url: 'https://github.com/tangnhatdang2810/Ecommerce-KLTN.git'

                script {
                    env.GIT_COMMIT_SHORT =
                        sh(script: "git rev-parse --short HEAD",
                           returnStdout: true).trim()
                }
            }
        }

    // =================================================
    // UNIT TEST (PARALLEL)
    // =================================================
        stage('Unit Test - Java Services') {
            steps {
                script {
                    def services = [
                        'authservice','cartservice','checkoutservice',
                        'paymentservice','productcatalogservice',
                        'shippingservice','apigateway'
                    ]

                    def jobs = [:]

                    for (svc in services) {
                        def s = svc
                        jobs["Test ${s}"] = {
                            dir("src/${s}") {
                                sh "mvn test -B"
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }

    // =================================================
    // BUILD PACKAGE (PARALLEL)
    // =================================================
        stage('Build Package') {
            steps {
                script {
                    def services = [
                        'authservice','cartservice','checkoutservice',
                        'paymentservice','productcatalogservice',
                        'shippingservice','apigateway'
                    ]

                    def jobs = [:]

                    for (svc in services) {
                        def s = svc
                        jobs["Build ${s}"] = {
                            dir("src/${s}") {
                                sh "mvn clean package -DskipTests -B"
                            }
                        }
                    }
                    parallel jobs
                }
            }
        }

    // =================================================
    // SONARQUBE (SAST)
    // =================================================
        stage('SonarQube Scan') {
            steps {
                script {
                    def services = [
                        'authservice','cartservice','checkoutservice',
                        'paymentservice','productcatalogservice',
                        'shippingservice','apigateway'
                    ]

                    withSonarQubeEnv('sonarqube-server') {
                        for (svc in services) {
                            dir("src/${svc}") {
                                sh """
                                mvn sonar:sonar \
                                  -Dsonar.projectKey=ecommerce-kltn-${svc}
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Quality Gate') {
            steps {
                timeout(time: 10, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

    // =================================================
    // OWASP DEPENDENCY CHECK (SCA)
    // =================================================
        stage('OWASP Dependency Check') {
            steps {
                // Sử dụng dấu nháy kép "" thay vì nháy đơn '' để tránh lỗi nội suy chuỗi nếu cần
                dependencyCheck additionalArguments: """
                    --scan './src'
                    --format 'ALL'
                    --out '.'
                """, 
                odcInstallation: 'dependency-check'

                script {
                    // Lệnh này sẽ giúp bạn debug: Tìm xem file thực sự nằm ở đâu
                    sh 'find . -name "dependency-check-report.xml"'
                }
        
                // Luôn sử dụng pattern quét sâu để Jenkins tự nhặt file
                dependencyCheckPublisher pattern: '**/dependency-check-report.xml'
            }
        }

    // =================================================
    // DOCKER BUILD
    // =================================================
        stage('Docker Build Images') {
            steps {
                script {
                    def services = [
                        'authservice','cartservice','checkoutservice',
                        'paymentservice','productcatalogservice',
                        'shippingservice','apigateway','frontend'
                    ]

                    for (svc in services) {
                        def image =
                          "${DOCKER_REGISTRY}/${IMAGE_PREFIX}-${svc}"

                        dir("src/${svc}") {
                            sh """
                            docker build \
                              -t ${image}:${env.GIT_COMMIT_SHORT} \
                              -t ${image}:latest .
                            """
                        }
                    }
                }
            }
        }

    // =================================================
    // TRIVY SCAN (PARALLEL + OPTIMIZED)
    // =================================================
        stage('Trivy Scan Docker Images') {
            steps {
                script {

                    def services = [
                        'authservice','cartservice','checkoutservice',
                        'paymentservice','productcatalogservice',
                        'shippingservice','apigateway','frontend'
                    ]

                    def scans = [:]

                    for (svc in services) {
                        def s = svc
                        scans["Scan ${s}"] = {

                            def image =
                              "${DOCKER_REGISTRY}/${IMAGE_PREFIX}-${s}:${env.GIT_COMMIT_SHORT}"

                            sh """
                            trivy image \
                              --cache-dir \$TRIVY_CACHE_DIR \
                              --skip-db-update \
                              --skip-java-db-update \
                              --severity HIGH,CRITICAL \
                              --exit-code 0 \
                              --format table \
                              ${image}
                            """
                        }
                    }

                    parallel scans
                }
            }
        }

    // =================================================
    // PUSH DOCKER IMAGES
    // =================================================
        stage('Push Images') {
            steps {
                script {

                    def services = [
                        'authservice','cartservice','checkoutservice',
                        'paymentservice','productcatalogservice',
                        'shippingservice','apigateway','frontend'
                    ]

                    withCredentials([usernamePassword(
                        credentialsId: 'dockerhub-creds',
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PASS'
                    )]) {

                        sh 'echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin'

                        for (svc in services) {
                            def image =
                              "${DOCKER_REGISTRY}/${IMAGE_PREFIX}-${svc}"

                            sh """
                            docker push ${image}:${env.GIT_COMMIT_SHORT}
                            docker push ${image}:latest
                            """
                        }
                    }
                }
            }
        }

    // =================================================
    // DAST - OWASP ZAP
    // =================================================
        stage('DAST - OWASP ZAP') {
            steps {
                sh '''
                docker compose up -d

                echo "Waiting application..."
                sleep 30

                docker run --rm \
                  --network host \
                  -v $(pwd):/zap/wrk \
                  zaproxy/zap-stable \
                  zap-baseline.py \
                  -t http://localhost:8080 \
                  -r zap-report.html || true

                docker compose down
                '''
            }
        }
    }

    // =================================================
    // CLEANUP
    // =================================================
    post {
        always {
            sh '''
            echo "===== CLEAN DOCKER ====="
            docker system prune -af || true
            docker builder prune -af || true

            echo "===== CLEAN TMP ====="
            rm -rf /tmp/trivy-* || true
            '''

            archiveArtifacts artifacts: '**/*.html',
                              allowEmptyArchive: true
        }
    }
}