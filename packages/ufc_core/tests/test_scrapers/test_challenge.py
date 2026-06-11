"""Tests for the UFCStats proof-of-work anti-bot challenge solver.

UFCStats serves a JS interstitial ("Checking your browser…") that computes a
SHA-256 proof-of-work and POSTs it to /__c to obtain a session cookie. requests
cannot run JS, so get_soup must detect the interstitial, solve the PoW, submit
it, and retry. These tests cover the two pure pieces of that flow.
"""

import hashlib

from ufc_core.scrapers.ufcstats import _extract_challenge, _solve_pow

# A faithful, trimmed copy of the interstitial UFCStats returns (status 200).
CHALLENGE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Loading…</title><meta name="robots" content="noindex">
</head><body>
<p>Checking your browser…</p>
<noscript>This site requires JavaScript.</noscript>
<script>
function sha256(s){/* ... */}
var nonce="0e43728a3cc1c110",
    target=new Array(2+1).join('0');
var n=0;
while(sha256(nonce+':'+n).slice(0,target.length)!==target){n++;}
var xhr=new XMLHttpRequest();
xhr.open('POST',"/__c",true);
xhr.send('nonce='+encodeURIComponent(nonce)+'&n='+n);
</script>
</body></html>"""

# A normal fighters-list page (what we get AFTER passing the challenge).
NORMAL_HTML = """<html><body><table class="b-statistics__table">
<tr><th>First</th></tr>
<tr><td><a href="http://ufcstats.com/fighter-details/abc">Jon</a></td></tr>
</table></body></html>"""


def test_solve_pow_produces_hash_with_required_leading_zeros():
    n = _solve_pow("0e43728a3cc1c110", 2)
    digest = hashlib.sha256(f"0e43728a3cc1c110:{n}".encode()).hexdigest()
    assert digest.startswith("00")
    assert isinstance(n, int) and n >= 0


def test_extract_challenge_parses_interstitial():
    out = _extract_challenge(CHALLENGE_HTML)
    assert out is not None
    nonce, zeros, post_path = out
    assert nonce == "0e43728a3cc1c110"
    assert zeros == 2
    assert post_path == "/__c"


def test_extract_challenge_returns_none_for_normal_page():
    assert _extract_challenge(NORMAL_HTML) is None
