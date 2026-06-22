import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "generate_search_env_template.py"
    spec = importlib.util.spec_from_file_location("generate_search_env_template", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_template_for_exa_http() -> None:
    module = _load_module()

    rendered = module.build_template("exa", "http")

    assert "SEARCH_PROVIDER_MODE=exa" in rendered
    assert "EXA_API_KEY=YOUR_EXA_API_KEY" in rendered
    assert "CONTENT_EXTRACTION_PROVIDER=http" in rendered


def test_main_defaults_to_tavily_http_template() -> None:
    module = _load_module()
    stdout = io.StringIO()

    with redirect_stdout(stdout):
        result = module.main([])

    output = stdout.getvalue()
    assert result == 0
    assert "SEARCH_PROVIDER_MODE=tavily" in output
    assert "TAVILY_API_KEY=YOUR_TAVILY_API_KEY" in output


def test_main_prints_template_with_cli_args() -> None:
    module = _load_module()
    stdout = io.StringIO()

    with redirect_stdout(stdout):
        result = module.main(["brave", "jina"])

    output = stdout.getvalue()
    assert result == 0
    assert "SEARCH_PROVIDER_MODE=brave" in output
    assert "BRAVE_API_KEY=YOUR_BRAVE_API_KEY" in output
    assert "CONTENT_EXTRACTION_PROVIDER=jina" in output


def test_main_reports_unsupported_provider() -> None:
    module = _load_module()
    stderr = io.StringIO()

    with redirect_stderr(stderr):
        result = module.main(["unknown-provider"])

    assert result == 1
    assert "Unsupported search provider" in stderr.getvalue()


def test_main_can_write_template_to_file(tmp_path: Path) -> None:
    module = _load_module()
    output_path = tmp_path / ".env"
    stdout = io.StringIO()

    with redirect_stdout(stdout):
        result = module.main(["tavily", "http", "--write", str(output_path)])

    assert result == 0
    assert output_path.exists()
    assert "SEARCH_PROVIDER_MODE=tavily" in output_path.read_text(encoding="utf-8")
    assert "Wrote template to" in stdout.getvalue()


def test_main_reports_missing_write_path() -> None:
    module = _load_module()
    stderr = io.StringIO()

    with redirect_stderr(stderr):
        result = module.main(["exa", "http", "--write"])

    assert result == 1
    assert "Missing path after --write" in stderr.getvalue()
