"""The artifact page must keep the app's code, drop what an artifact can't use, and never fetch other hosts."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from build_artifact import transform

SOURCE = open(os.path.join(os.path.dirname(__file__), "..", "index.html"), encoding="utf-8").read()
PAGE = transform(SOURCE)


def test_no_fetch_of_other_hosts_and_no_page_wrapper():
    assert not re.search(r"fetch\(\s*['\"]https?://", PAGE) and "raw.githubusercontent.com" in PAGE.split("</script>")[0]
    assert PAGE.count("fetch(") == 1                       # only the relative snapshot
    for tag in ("<!DOCTYPE", "<html", "<head", "<body", "<base", "rel=\"icon\""):
        assert tag.lower() not in PAGE.lower()


def test_fonts_use_a_link_not_an_import():
    assert "@import" not in PAGE and "fonts.googleapis.com/css2" in PAGE.split("<style>")[0]


def test_title_manifest_and_dark_scheme():
    assert PAGE.startswith("<title>Tickreja</title>")
    assert '"permissions": ["full-access"]' in PAGE and "color-scheme:dark" in PAGE


def test_app_code_is_kept():
    for name in ("renderHome", "renderPortfolio", "renderStockDetail", "renderPlan", "renderMarketPanel"):
        assert f"function {name}" in PAGE
    assert PAGE.count("onclick=") >= SOURCE.count("onclick=")


def test_loader_comes_before_the_app_script_and_scripts_balance():
    assert PAGE.index("function fetchDashboard") < PAGE.index("// ── UTILS")
    assert PAGE.count("<script") == PAGE.count("</script>")


def test_live_download_runs_one_fixed_command():
    assert PAGE.count("childProcess.spawn(") == 1 and "exec(" not in PAGE.replace("regexec(", "")
    assert "'-fsSL', '--max-time', '30', LIVE_URL" in PAGE
