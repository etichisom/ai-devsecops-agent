// Unit tests for SecurityGate. Run with:
//   groovy -cp ci/jenkins/src ci/jenkins/test/SecurityGateTest.groovy

import io.github.etichisom.devsecops.SecurityGate

int passed = 0
def check = { String name, Closure body ->
    body()
    passed++
    println "ok - ${name}"
}

Map clean = [CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 2, INFO: 1]
Map medium = [CRITICAL: 0, HIGH: 0, MEDIUM: 3, LOW: 0, INFO: 0]
Map high = [CRITICAL: 0, HIGH: 1, MEDIUM: 3, LOW: 0, INFO: 0]

check('rank orders severities and ignores case/whitespace') {
    assert SecurityGate.rank('info') < SecurityGate.rank('LOW')
    assert SecurityGate.rank(' critical ') == 4
}

check('unknown severity is rejected') {
    try {
        SecurityGate.rank('urgent')
        assert false: 'expected IllegalArgumentException'
    } catch (IllegalArgumentException expected) {
        assert expected.message.contains('urgent')
    }
}

check('countAtOrAbove sums matching buckets') {
    assert SecurityGate.countAtOrAbove(high, 'medium') == 4
    assert SecurityGate.countAtOrAbove(high, 'high') == 1
    assert SecurityGate.countAtOrAbove(high, 'critical') == 0
}

check('none or empty threshold never counts') {
    assert SecurityGate.countAtOrAbove(high, 'none') == 0
    assert SecurityGate.countAtOrAbove(high, '') == 0
    assert SecurityGate.countAtOrAbove(high, null) == 0
}

check('missing and null buckets count as zero') {
    assert SecurityGate.countAtOrAbove([HIGH: null, LOW: 1], 'low') == 1
}

check('buildResult picks FAILURE over UNSTABLE over SUCCESS') {
    assert SecurityGate.buildResult(high, 'high', 'medium') == 'FAILURE'
    assert SecurityGate.buildResult(medium, 'high', 'medium') == 'UNSTABLE'
    assert SecurityGate.buildResult(clean, 'high', 'medium') == 'SUCCESS'
    assert SecurityGate.buildResult(high, 'none', 'none') == 'SUCCESS'
}

check('describe lists every level, most severe first') {
    assert SecurityGate.describe(high) == 'critical=0, high=1, medium=3, low=0, info=0'
}

println "${passed} tests passed"
