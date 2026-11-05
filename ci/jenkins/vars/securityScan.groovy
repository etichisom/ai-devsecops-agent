import io.github.etichisom.devsecops.SecurityGate

/**
 * Jenkins shared-library step: run security scanners with devsecops-agent, publish the reports
 * and set the build result from the findings.
 *
 * Usage in a Jenkinsfile:
 *
 *   securityScan(
 *       path: '.',
 *       scanners: 'semgrep,bandit,pip-audit,gitleaks',
 *       failOn: 'high',          // FAILURE if any finding is at or above this severity
 *       warnOn: 'medium',        // UNSTABLE if any finding is at or above this severity
 *       aiSummary: true,         // add a Claude-written triage summary to the report
 *       credentialsId: 'anthropic-api-key'
 *   )
 *
 * Requires: devsecops-agent and the chosen scanners on the agent's PATH,
 * and the Pipeline Utility Steps plugin (readJSON).
 *
 * @return the severity summary map, e.g. [CRITICAL: 0, HIGH: 1, ...]
 */
def call(Map config = [:]) {
    String path = config.get('path', '.')
    String scanners = config.get('scanners', 'semgrep,bandit,pip-audit,gitleaks')
    String failOn = config.get('failOn', 'high')
    String warnOn = config.get('warnOn', 'medium')
    String outDir = config.get('outDir', 'reports')
    boolean aiSummary = config.get('aiSummary', false)

    // The CLI never fails the step itself (--fail-on none); the gate below decides
    // between FAILURE and UNSTABLE, which a plain exit code cannot express.
    List<String> args = ['devsecops-agent', 'scan', path, '--scanners', scanners, '--out', outDir, '--fail-on', 'none']
    if (aiSummary) {
        args << '--ai-summary'
    }
    String command = args.collect { shellQuote(it) }.join(' ')

    if (aiSummary && config.credentialsId) {
        withCredentials([string(credentialsId: config.credentialsId, variable: 'ANTHROPIC_API_KEY')]) {
            sh command
        }
    } else {
        sh command
    }

    archiveArtifacts artifacts: "${outDir}/security-*", fingerprint: true
    junit testResults: "${outDir}/security-junit.xml", allowEmptyResults: true

    Map summary = readJSON(file: "${outDir}/security-report.json").summary
    String result = SecurityGate.buildResult(summary, failOn, warnOn)
    String message = "Security findings: ${SecurityGate.describe(summary)}"
    echo "${message} -> ${result}"

    if (result == 'FAILURE') {
        error("${message}. Failing because findings are at or above '${failOn}'.")
    } else if (result == 'UNSTABLE') {
        unstable("${message}. Marked unstable because findings are at or above '${warnOn}'.")
    }
    return summary
}

private static String shellQuote(String value) {
    return "'" + value.replace("'", "'\"'\"'") + "'"
}
