"""READ-ONLY MLflow Registry integration checks for cnc-wearpoint-multitask.

Skipped by default. Runs only when BOTH are set:
  MODEL_LIFECYCLE_INTEGRATION=1
  MLFLOW_TRACKING_URI=<tracking server>
and the ``mlflow`` package is importable (it is not in the backend venv; use a
venv with mlflow==3.18.0). Use a READ-ONLY MLflow user. Recommended: run on the
App VM against the local server, not through the public proxy.

Exact command (Git Bash, from the backend repo root):

  MODEL_LIFECYCLE_INTEGRATION=1 \
  MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  MLFLOW_TRACKING_USERNAME=<readonly-user> MLFLOW_TRACKING_PASSWORD=<readonly-pass> \
  python -m pytest -q -rs tests/model_lifecycle/test_registry_integration.py

Optional overrides: LIFECYCLE_MODEL_NAME (default cnc-wearpoint-multitask),
LIFECYCLE_EXPECT_CANDIDATE_VERSION (default 1),
LIFECYCLE_EXPECT_CANDIDATE_OPT_VERSION (default 2).

Safety: only GET-style client calls are used (get_registered_model,
get_model_version_by_alias, get_model_version, get_model_version_download_uri,
artifact listing / reading MLmodel text). The client is wrapped in a proxy that
refuses any other method, so set/delete alias, transition, create, update and
delete can never be called from this module. Reading MLmodel downloads only that
small text file to a local temp dir; model weights are never downloaded.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("MODEL_LIFECYCLE_INTEGRATION") != "1" or not os.getenv("MLFLOW_TRACKING_URI"),
    reason="read-only Registry integration: set MODEL_LIFECYCLE_INTEGRATION=1 and MLFLOW_TRACKING_URI",
)

MODEL_NAME = os.getenv("LIFECYCLE_MODEL_NAME", "cnc-wearpoint-multitask")
EXPECTED_ALIASES = {
    "candidate": os.getenv("LIFECYCLE_EXPECT_CANDIDATE_VERSION", "1"),
    "candidate-opt": os.getenv("LIFECYCLE_EXPECT_CANDIDATE_OPT_VERSION", "2"),
}
VERSIONS = sorted(set(EXPECTED_ALIASES.values()), key=int)
# Output columns ml/serving/service.py reads from model.predict(...).iloc[0].
SERVICE_OUTPUT_COLUMNS = {"predicted_wear_um", "predicted_type", "flank_wear_probability",
                          "epoch", "window_count", "sampling_hz"}

READ_ONLY_METHODS = frozenset({
    "get_registered_model",
    "get_model_version",
    "get_model_version_by_alias",
    "get_model_version_download_uri",
})


class ReadOnlyClient:
    """Allow-list proxy around MlflowClient; any non-GET method raises."""

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        if name not in READ_ONLY_METHODS:
            raise AssertionError(f"MlflowClient.{name} is not allowed in read-only tests")
        return getattr(self._client, name)


@pytest.fixture(scope="module")
def mlflow_mod():
    return pytest.importorskip("mlflow", reason="mlflow is not installed in this interpreter")


@pytest.fixture(scope="module")
def client(mlflow_mod):
    from mlflow.tracking import MlflowClient

    return ReadOnlyClient(MlflowClient(tracking_uri=os.environ["MLFLOW_TRACKING_URI"]))


def _download_uri(client, version):
    return client.get_model_version_download_uri(MODEL_NAME, version)


def _mlmodel(mlflow_mod, client, version):
    import yaml

    text = mlflow_mod.artifacts.load_text(_download_uri(client, version).rstrip("/") + "/MLmodel")
    return yaml.safe_load(text)


def test_registered_model_exists_with_expected_aliases(client):
    model = client.get_registered_model(MODEL_NAME)
    assert model.name == MODEL_NAME
    aliases = {k: str(v) for k, v in (model.aliases or {}).items()}
    for alias, version in EXPECTED_ALIASES.items():
        assert aliases.get(alias) == version, aliases


@pytest.mark.parametrize("alias", sorted(EXPECTED_ALIASES))
def test_alias_resolves_to_expected_ready_version(client, alias):
    mv = client.get_model_version_by_alias(MODEL_NAME, alias)
    assert str(mv.version) == EXPECTED_ALIASES[alias]
    assert mv.status == "READY"


@pytest.mark.parametrize("version", VERSIONS)
def test_model_version_is_ready(client, version):
    mv = client.get_model_version(MODEL_NAME, version)
    assert str(mv.version) == version
    assert mv.status == "READY"
    assert mv.source


@pytest.mark.parametrize("version", VERSIONS)
def test_version_artifacts_contain_mlmodel(mlflow_mod, client, version):
    entries = mlflow_mod.artifacts.list_artifacts(artifact_uri=_download_uri(client, version))
    names = {os.path.basename(entry.path.rstrip("/")) for entry in entries}
    assert "MLmodel" in names, sorted(names)


@pytest.mark.parametrize("version", VERSIONS)
def test_version_is_loadable_by_current_service_contract(mlflow_mod, client, version):
    """service.py uses mlflow.pyfunc.load_model and reads named output columns.

    A failure here means the version is NOT a drop-in for the current Serving
    (e.g. a torch.export-only flavor). It is a compatibility finding, not a
    Registry error.
    """
    mlmodel = _mlmodel(mlflow_mod, client, version)
    flavors = mlmodel.get("flavors", {})
    assert "python_function" in flavors, sorted(flavors)
    outputs = mlmodel.get("signature", {}).get("outputs")
    assert outputs, "MLmodel has no output signature"
    import json

    columns = {col.get("name") for col in json.loads(outputs)}
    assert SERVICE_OUTPUT_COLUMNS <= columns, sorted(columns)
