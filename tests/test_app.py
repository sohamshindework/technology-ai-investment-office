"""Investment workflows: four-page navigation, applied state, filtering and safe review."""

import io
import json
import zipfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def open_app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_navigation_and_live_budget_recalculation():
    app = open_app()
    assert not app.exception
    assert app.title[0].value == "Technology Investment Portfolio"
    assert app.radio[0].options == ["Portfolio", "Scenario Lab", "Delivery Plan", "Decision Brief"]
    assert any("Evaluate opportunities. Allocate capital. Plan implementation." in e.value for e in app.markdown)
    assert any("Technology &amp; AI Investment Strategy" in e.value for e in app.sidebar.markdown)
    assert app.metric[0].value == "€48.1m"
    assert app.selectbox(key="case_selector").value.endswith("dhl_supply_chain")
    assert len(app.selectbox(key="case_selector").options) == 3
    assert any("mailto:sohamshindework@gmail.com" in e.value for e in app.markdown)
    assert any("Developed by Soham Shinde." in e.value for e in app.markdown)
    app.radio[0].set_value("Scenario Lab").run()
    app.slider(key="input_budget_scale").set_value(0.5)
    # Draft form edits stay in the browser until submit; do not force an artificial rerun.
    # The applied analysis and export state must remain unchanged before that submit.
    assert app.metric[1].delta == "of €60.0m envelope"
    button(app, "Recalculate portfolio").click().run()
    assert not app.exception
    assert app.metric[1].delta == "of €30.0m envelope"
    app.slider(key="input_extra_delay_months").set_value(6)
    button(app, "Recalculate portfolio").click().run()
    assert not app.exception
    assert app.metric[0].value != "€48.1m"
    assert app.session_state["previous_scenario"]["npv"] > app.session_state["last_summary"]["npv"]
    for page in ["Portfolio", "Delivery Plan", "Decision Brief"]:
        app.radio[0].set_value(page).run()
        assert not app.exception, page
    downloads = app.get("download_button")
    assert len(downloads) >= 5
    labels = {item.label for item in downloads}
    assert "Download Excel Analysis" in labels
    assert "Download Investment Committee Report" in labels


def test_portfolio_filter_empty_state():
    app = open_app()
    assert any(item.label == "Research a potential investment" for item in app.expander)
    assert any(item.label == "Authorized report · PDF, TXT or Markdown" for item in app.get("file_uploader"))
    app.text_input(key="candidate_search").set_value("no-such-initiative").run()
    assert not app.exception
    assert any("No initiatives match" in e.value for e in app.info)


def test_research_document_requires_review_and_stays_out_of_financial_model():
    app = open_app()
    baseline = app.metric[0].value
    app.text_input(key="research_title_dhl_supply_chain").set_value("Authorized operations report").run()
    app.get("file_uploader")[0].upload(
        "report.txt",
        b"The network uses warehouse automation and a data integration platform across eligible sites.",
        "text/plain",
    ).run()
    app.checkbox(key="research_authorized_dhl_supply_chain").check().run()
    button(app, "Analyze document").click().run()
    assert not app.exception
    assert any("warehouse automation" in element.value for element in app.markdown)
    proposal = json.loads(app.session_state["research_proposal_json"])
    assert proposal["review_status"] == "draft"
    assert proposal["approved_for_financial_model"] is False
    assert app.metric[0].value == baseline

    app.text_area(key="research_review_note_dhl_supply_chain").set_value(
        "Validate scope and baseline with the operating owner."
    ).run()
    button(app, "Record research review").click().run()
    reviewed = json.loads(app.session_state["research_proposal_json"])
    assert reviewed["review_status"] == "accepted_for_validation"
    assert reviewed["approved_for_financial_model"] is False
    assert app.metric[0].value == baseline


def test_governance_unknown_answers_are_visible_and_excluded():
    app = open_app()
    app.session_state["overrides"] = {"LABOUR_FORECAST": {}}
    app.radio[0].set_value("Delivery Plan").run()
    assert not app.exception
    table = next(frame.value for frame in app.dataframe if "Unknown answers" in frame.value.columns)
    row = table[table.Initiative.str.startswith("Site labour-demand")].iloc[0]
    assert row["Excluded"] and row["Unknown answers"] > 0
    assert [tab.label for tab in app.tabs] == ["Rollout", "Governance", "Benefits"]
    assert len(app.get("file_uploader")) == 1
    assert any("Observed benefits are unavailable" in e.value for e in app.info)


def test_scenario_reset_case_isolation_and_current_exports(monkeypatch):
    from frontend.pages import brief

    original = brief.bundle
    exported = []

    def capture(a):
        data = original(a)
        exported.append((a.portfolio.mean, data))
        return data

    monkeypatch.setattr(brief, "bundle", capture)
    app = open_app()
    app.radio[0].set_value("Scenario Lab").run()
    app.slider(key="input_extra_delay_months").set_value(6)
    button(app, "Recalculate portfolio").click().run()
    assert app.metric[0].value == "€39.3m"
    app.radio[0].set_value("Decision Brief").run()
    assert not app.exception
    npv, data = exported[-1]
    with zipfile.ZipFile(io.BytesIO(data)) as pack:
        metadata = json.loads(pack.read("settings.json"))
        assert metadata["deployment_delay_quarters"] == 2
        assert "€39.30m" in pack.read("memo.md").decode()
        assert metadata["company"] == "DHL Supply Chain"
    assert abs(npv - app.session_state["last_summary"]["npv"]) < 1e-8
    app.radio[0].set_value("Scenario Lab").run()
    button(app, "Return to reference assumptions").click().run()
    assert not app.exception
    assert app.metric[0].value == "€48.1m"
    assert app.slider(key="input_extra_delay_months").value == 0
    assert app.session_state["overrides"] == {}
    # Changing cases must isolate all active assumptions and questionnaire answers.
    app.slider(key="input_extra_delay_months").set_value(6)
    button(app, "Recalculate portfolio").click().run()
    app.session_state["overrides"] = {"LABOUR_FORECAST": {}}
    app.selectbox(key="case_selector").set_value(str(ROOT / "cases/allianz")).run()
    assert not app.exception
    assert app.session_state["active_config"]["extra_delay_months"] == 0
    assert app.session_state["overrides"] == {}
    assert app.session_state["previous_scenario"] is None
    app.selectbox(key="case_selector").set_value(str(ROOT / "cases/dhl_supply_chain")).run()
    assert not app.exception
    assert app.metric[0].value == "€48.1m"


def test_zero_investment_state_and_review_form_validation():
    app = open_app()
    app.radio[0].set_value("Scenario Lab").run()
    app.slider(key="input_benefit_factor").set_value(0.0)
    button(app, "Recalculate portfolio").click().run()
    app.radio[0].set_value("Portfolio").run()
    assert not app.exception
    assert any("Hold investment" in e.value for e in app.markdown)
    app.radio[0].set_value("Delivery Plan").run()
    assert not app.exception
    assert any("No deployment activities" in e.value for e in app.info)
    button(app, "Save review record").click().run()
    assert any("Reviewer, evidence and uncertainty are required" in e.value for e in app.error)


def test_imported_actuals_follow_navigation_and_current_exports(monkeypatch, tmp_path):
    from frontend.pages import brief
    from invest_engine import load_case
    from invest_engine.benefits import observation_template
    from invest_engine.service import analyse
    from invest_engine.store import Store

    monkeypatch.setattr(brief, "Store", lambda _: Store(tmp_path / "records.sqlite3"))
    analysis = analyse(load_case(ROOT / "cases/dhl_supply_chain"))
    actuals = observation_template(analysis.benefits)
    actuals["observed_benefit_EUR_k"] = 123.0
    actuals["source"] = "Management benefits ledger"
    actuals["observation_date"] = actuals.reporting_period_end
    actuals["confidence"] = "high"
    actuals["is_simulated"] = False
    packs = []
    original = brief.bundle

    def capture(a):
        packs.append(original(a))
        return packs[-1]

    monkeypatch.setattr(brief, "bundle", capture)
    app = open_app()
    app.session_state["benefits_actuals"] = actuals.to_csv(index=False).encode()
    app.radio[0].set_value("Delivery Plan").run()
    assert not app.exception
    assert any("User-provided observations" in e.value for e in app.info)
    app.radio[0].set_value("Decision Brief").run()
    with zipfile.ZipFile(io.BytesIO(packs[-1])) as pack:
        import pandas as pd

        exported = pd.read_csv(io.BytesIO(pack.read("benefits_REPORTED.csv")))
        assert (exported.observed_benefit_EUR_k == 123.0).all()
        assert not exported.is_simulated.any()
        assert "user-provided, unverified observations" in pack.read("memo.md").decode()
    button(app, "Save current analysis").click().run()
    assert any("current investment analysis is saved" in e.value for e in app.success)
    actuals["observed_benefit_EUR_k"] = 456.0
    app.session_state["benefits_actuals"] = actuals.to_csv(index=False).encode()
    app.run()
    assert not any("current investment analysis is saved" in e.value for e in app.success)
    # Imported rows for deferred investments must not break a changed recommendation.
    app.radio[0].set_value("Scenario Lab").run()
    app.slider(key="input_benefit_factor").set_value(0.0)
    button(app, "Recalculate portfolio").click().run()
    assert not app.exception
    app.radio[0].set_value("Delivery Plan").run()
    assert not app.exception
    button(app, "Clear observations").click().run()
    assert not app.exception
    assert "benefits_actuals" not in app.session_state
