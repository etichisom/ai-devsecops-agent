package io.github.etichisom.devsecops

/**
 * Decides the Jenkins build result from a security report summary.
 *
 * The summary is the "summary" object of security-report.json, e.g.
 *   [CRITICAL: 0, HIGH: 1, MEDIUM: 3, LOW: 2, INFO: 0]
 *
 * Written with plain loops (no closures) so it behaves the same inside Jenkins' CPS
 * interpreter and in a plain Groovy unit test.
 */
class SecurityGate implements Serializable {

    static final List<String> LEVELS = ['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

    static int rank(String severity) {
        String key = severity == null ? '' : severity.trim().toUpperCase()
        int index = LEVELS.indexOf(key)
        if (index < 0) {
            throw new IllegalArgumentException("Unknown severity: ${severity}")
        }
        return index
    }

    static boolean isDisabled(String threshold) {
        return threshold == null || threshold.trim().isEmpty() || threshold.trim().equalsIgnoreCase('none')
    }

    /** Number of findings at or above the threshold severity. */
    static int countAtOrAbove(Map summary, String threshold) {
        if (isDisabled(threshold)) {
            return 0
        }
        int minimum = rank(threshold)
        int total = 0
        for (Object key : summary.keySet()) {
            if (rank(key as String) >= minimum) {
                total += (summary.get(key) ?: 0) as int
            }
        }
        return total
    }

    /** FAILURE beats UNSTABLE beats SUCCESS. */
    static String buildResult(Map summary, String failOn, String warnOn) {
        if (countAtOrAbove(summary, failOn) > 0) {
            return 'FAILURE'
        }
        if (countAtOrAbove(summary, warnOn) > 0) {
            return 'UNSTABLE'
        }
        return 'SUCCESS'
    }

    static String describe(Map summary) {
        List<String> parts = []
        for (int i = LEVELS.size() - 1; i >= 0; i--) {
            String level = LEVELS[i]
            parts << "${level.toLowerCase()}=${summary.get(level) ?: 0}".toString()
        }
        return parts.join(', ')
    }
}
