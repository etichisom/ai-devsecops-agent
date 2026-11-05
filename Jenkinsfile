// Declarative pipeline for Jenkins / CloudBees CI.
//
// Loads the securityScan step from this repo's own shared library (ci/jenkins), so the
// library code and the pipeline that uses it are versioned together.
// Needs: Docker Pipeline, Pipeline Utility Steps and JUnit plugins; a Docker-capable agent;
// optional secret-text credential 'anthropic-api-key' for the AI triage summary.

library identifier: "devsecops-agent-lib@${env.BRANCH_NAME ?: 'main'}",
        retriever: modernSCM([
            $class       : 'GitSCMSource',
            remote       : 'https://github.com/etichisom/ai-devsecops-agent.git',
            libraryPath  : 'ci/jenkins/'
        ])

pipeline {
    agent none

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
    }

    parameters {
        choice(name: 'FAIL_ON', choices: ['high', 'critical', 'medium', 'low', 'none'],
               description: 'Fail the build on findings at or above this severity')
        booleanParam(name: 'AI_SUMMARY', defaultValue: false,
                     description: 'Add a Claude-written triage summary (needs the anthropic-api-key credential)')
    }

    environment {
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
        PIP_CACHE_DIR = "${WORKSPACE}/.pip-cache"
    }

    stages {
        stage('Python checks') {
            agent { docker { image 'python:3.12-slim'; reuseNode true } }
            stages {
                stage('Install') {
                    steps {
                        sh '''
                            python -m venv .venv
                            . .venv/bin/activate
                            pip install -e '.[dev,scanners]' cyclonedx-bom
                        '''
                    }
                }
                stage('Lint') {
                    steps {
                        sh '. .venv/bin/activate && ruff check src tests && ruff format --check src tests'
                    }
                }
                stage('Unit & integration tests') {
                    steps {
                        sh '. .venv/bin/activate && pytest --junitxml=reports/pytest.xml --cov --cov-report=xml:reports/coverage.xml'
                    }
                    post {
                        always {
                            junit 'reports/pytest.xml'
                            archiveArtifacts artifacts: 'reports/coverage.xml', allowEmptyArchive: true
                        }
                    }
                }
                stage('Security scan') {
                    steps {
                        // gitleaks runs in GitLab/GitHub; this agent image only has the Python scanners.
                        withEnv(["PATH+VENV=${WORKSPACE}/.venv/bin"]) {
                            securityScan(
                                path: '.',
                                scanners: 'semgrep,bandit,pip-audit',
                                failOn: params.FAIL_ON,
                                warnOn: 'medium',
                                aiSummary: params.AI_SUMMARY,
                                credentialsId: 'anthropic-api-key'
                            )
                        }
                    }
                }
                stage('SBOM') {
                    steps {
                        sh '. .venv/bin/activate && cyclonedx-py environment --output-format JSON --output-file reports/sbom.cdx.json .venv'
                        archiveArtifacts artifacts: 'reports/sbom.cdx.json', fingerprint: true
                    }
                }
            }
        }

        stage('Container image') {
            agent any
            steps {
                sh "docker build -t devsecops-agent:${env.BUILD_NUMBER} ."
                sh """
                    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
                        aquasec/trivy:0.57.1 image --exit-code 1 --severity HIGH,CRITICAL \
                        --ignore-unfixed devsecops-agent:${env.BUILD_NUMBER}
                """
            }
        }
    }
}
