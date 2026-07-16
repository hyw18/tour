from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sources():
    return (
        (ROOT / "templates/player.html").read_text(encoding="utf-8"),
        (ROOT / "static/js/player.js").read_text(encoding="utf-8"),
        (ROOT / "static/css/style.css").read_text(encoding="utf-8"),
    )


def test_player_hud_has_one_identity_and_no_live_final_asset_metric():
    template, script, _ = sources()
    assert template.count('id="playerBadge"') == 1
    assert 'id="playerState"' not in template
    assert 'id="zoomCell"' not in template
    assert "즉시 종료 총재산" not in template
    assert "즉시 종료 총재산" not in script
    for element_id in ("topbarCash", "mainGuide", "roundStatus", "turnTimer", "openRankings", "openFinance"):
        assert f'id="{element_id}"' in template


def test_rankings_use_server_public_wealth_without_private_cash():
    template, script, _ = sources()
    assert 'id="rankingModal"' in template
    assert 'role="dialog"' in template
    ranking_renderer = script[script.index("function renderRankings"):script.index("function applyFinanceTab")]
    assert "state.public_wealth?.players" in ranking_renderer
    assert ".sort(" not in ranking_renderer
    assert "privateData" not in ranking_renderer
    assert "cash_won" not in ranking_renderer
    assert "total_asset_won" in ranking_renderer
    assert 'id="unrankedPlayers"' in template


def test_finance_details_are_reachable_in_one_accessible_dialog():
    template, script, _ = sources()
    assert template.count('id="assetPanel"') == 1
    assert template.count('id="settlementPanel"') == 1
    assert 'id="financeModal"' in template
    for tab in ("assets", "tax", "loan", "history"):
        assert f'data-finance-tab="{tab}"' in template
        assert f'data-finance-pane="{tab}"' in script or tab == "tax"
    assert "trapConfirmationFocus(event, financeModal)" in script
    assert "closePanelDialog(financeModal)" in script


def test_arrival_and_selection_have_distinct_semantics_and_auto_focus():
    _, script, css = sources()
    assert 'isActualArrival ? privateData?.pending_action : null' in script
    assert '"도착 칸" : "선택한 칸 · 행동은 실제 도착 칸 기준"' in script
    assert "authenticatedMe.position !== lastArrivalPosition" in script
    assert "focusArrivalInformation(authenticatedMe.position)" in script
    assert 'classList.add("current-turn-chip")' in script
    for selector in (".board-cell.arrival-cell", ".board-cell.selected-cell", ".arrival-focus-card", ".arrival-card-emphasis"):
        assert selector in css
    assert ".arrival-action-emphasis" in css


def test_player_dialogs_and_motion_preferences_are_styled():
    _, script, css = sources()
    assert ".panel-dialog" in css
    assert ".ranking-row" in css
    assert ".finance-tabs" in css
    assert ".timer-warning" in css
    assert ".timer-critical" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert 'event.key === "Escape"' in script
