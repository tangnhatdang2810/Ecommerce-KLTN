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

        stage('Checkout') {
            steps {
                git branch: 'main',
                    url: 'https://github.com/tangnhatdang2810/Ecommerce-KLTN.git'
                script {
                    env.GIT_COMMIT_SHORT = sh(script: "git rev-parse --short HEAD", returnStdout: true).trim()
                }
            }
        }

        // ═══════════════════════════════════════════════
        //  UNIT TEST - Java Services (Maven) - Parallel
        // ═══════════════════════════════════════════════
        stage('Unit Test - Java Services') {
            steps {
                script {
                    def javaServices = [
                        'authservice', 'cartservice', 'checkoutservice',
                        'paymentservice', 'productcatalogservice',
                        'shippingservice', 'apigateway'
                    ]
                    def testStages = [:]
                    for (svc in javaServices) {
                        def serviceName = svc
                        testStages["Test ${serviceName}"] = {
                            dir("src/${serviceName}") {
                                sh "mvn test -B"
                            }
                        }
                    }
                    parallel testStages
                }
            }
        }

        // ═══════════════════════════════════════════════
        //  BUILD - Java Services (Maven) - Parallel
        // ═══════════════════════════════════════════════
        stage('Build Package - Java Services') {
            steps {
                script {
                    def javaServices = [
                        'authservice', 'cartservice', 'checkoutservice',
                        'paymentservice', 'productcatalogservice',
                        'shippingservice', 'apigateway'
                    ]
                    def buildStages = [:]
                    for (svc in javaServices) {
                        def serviceName = svc
                        buildStages["Build ${serviceName}"] = {
                            dir("src/${serviceName}") {
                                sh "mvn clean package -DskipTests -B"
                            }
                        }
                    }
                    parallel buildStages
                }
            }
        }

        // ═══════════════════════════════════════════════
        //  SAST - SonarQube (từng service riêng project)
        // ═══════════════════════════════════════════════
        stage('SonarQube Scan (SAST)') {
            steps {
                script {
                    def javaServices = [
                        'authservice', 'cartservice', 'checkoutservice',
                        'paymentservice', 'productcatalogservice',
                        'shippingservice', 'apigateway'
                    ]
                    withSonarQubeEnv('sonarqube-server') {
                        for (svc in javaServices) {
                            dir("src/${svc}") {
                                sh """
                                mvn sonar:sonar \
                                  -Dsonar.projectKey=ecommerce-kltn-${svc} \
                                  -Dsonar.projectName=ecommerce-kltn-${svc}
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

        // ═══════════════════════════════════════════════
        //  DOCKER BUILD + TRIVY SCAN + PUSH (all 8 services)
        // ═══════════════════════════════════════════════
        stage('Docker Build & Trivy Scan & Push') {
            steps {
                script {
                    def allServices = [
                        'authservice', 'cartservice', 'checkoutservice',
                        'paymentservice', 'productcatalogservice',
                        'shippingservice', 'apigateway', 'frontend'
                    ]

                    withCredentials([usernamePassword(
                        credentialsId: 'dockerhub-creds',
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PASS'
                    )]) {
                        sh 'echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin'

                        for (svc in allServices) {
                            def imageName = "${DOCKER_REGISTRY}/${IMAGE_PREFIX}-${svc}"
                            def imageTag  = "${env.GIT_COMMIT_SHORT}"

                            // Docker Build
                            dir("src/${svc}") {
                                sh "docker build -t ${imageName}:${imageTag} -t ${imageName}:latest ."
                            }

                            // Trivy Image Scan
                            sh """
                            trivy image \
                              --cache-dir \$TRIVY_CACHE_DIR \
                              ${imageName}:${imageTag}
                            """

                            // Push to DockerHub
                            sh """
                            docker push ${imageName}:${imageTag}
                            docker push ${imageName}:latest
                            """
                        }
                    }
                }
            }
        }

        // ═══════════════════════════════════════════════
        //  DAST - OWASP ZAP (chạy app bằng docker-compose)
        // ═══════════════════════════════════════════════
        stage('DAST - OWASP ZAP') {
            steps {
                sh '''
                # Start toàn bộ services bằng docker-compose
                docker-compose up -d

                # Đợi app sẵn sàng (frontend ở port 8080)
                echo "Waiting for application to start..."
                sleep 30

                # ZAP baseline scan qua host network
                docker run --rm \
                  --network host \
                  -v $(pwd):/zap/wrk \
                  zaproxy/zap-stable \
                  zap-baseline.py \
                  -t http://localhost:8080 \
                  -r zap-report.html || true

                # Dọn dẹp
                docker-compose down
                '''
            }
        }

        // ═══════════════════════════════════════════════
        //  UPDATE K8S MANIFESTS (cho CD - ArgoCD sau này)
        //  Uncomment khi sẵn sàng làm CD
        // ═══════════════════════════════════════════════
        // stage('Update K8s Manifests & Push to Git') {
        //     steps {
        //         script {
        //             def allServices = [
        //                 'authservice', 'cartservice', 'checkoutservice',
        //                 'paymentservice', 'productcatalogservice',
        //                 'shippingservice', 'apigateway', 'frontend'
        //             ]
        //             for (svc in allServices) {
        //                 sh """
        //                 sed -i 's|image: .*${svc}.*|image: ${DOCKER_REGISTRY}/${IMAGE_PREFIX}-${svc}:${env.GIT_COMMIT_SHORT}|' \
        //                   kubernetes-manifests/${svc}.yaml
        //                 """
        //             }
        //             withCredentials([usernamePassword(
        //                 credentialsId: 'github-creds',
        //                 usernameVariable: 'GIT_USER',
        //                 passwordVariable: 'GIT_PASS'
        //             )]) {
        //                 sh '''
        //                 git config user.email "jenkins@ci.local"
        //                 git config user.name "Jenkins CI"
        //                 git add kubernetes-manifests/
        //                 git commit -m "ci: update image tags to ${GIT_COMMIT_SHORT}" || true
        //                 git push https://${GIT_USER}:${GIT_PASS}@github.com/tangnhatdang2810/Ecommerce-KLTN.git main
        //                 '''
        //             }
        //         }
        //     }
        // }
    }

    post {
        always {
            sh '''
            echo "===== CLEAN DOCKER ====="
            docker system prune -af || true
            docker builder prune -af || true

            echo "===== CLEAN TMP ====="
            rm -rf /tmp/trivy-* || true
            '''

            archiveArtifacts artifacts: '**/*.html', allowEmptyArchive: true
        }
    }
}
