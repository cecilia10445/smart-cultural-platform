from evaluation.real_image_smoke import run_smoke


def test_image_smoke_uses_temporary_file_and_reports_no_url(tmp_path):
    class Service:
        def generate_image_from_prompt(self, _prompt):
            return "https://provider.invalid/private-image"

    def persist(_url, directory):
        path = tmp_path / "image.png"
        path.write_bytes(b"image")
        return "/static/images/image_test.png"

    result = run_smoke(Service(), persist=persist)
    assert result["status"] == "failed"  # file intentionally is outside the supplied temporary directory
    assert "provider.invalid" not in str(result)


def test_image_smoke_success_reports_only_safe_counts(tmp_path):
    class Service:
        def generate_image_from_prompt(self, _prompt):
            return "https://provider.invalid/private-image"

    def persist(_url, directory):
        path = __import__("pathlib").Path(directory) / "image_test.png"
        path.write_bytes(b"image")
        return "/static/images/image_test.png"

    result = run_smoke(Service(), persist=persist)
    assert result["status"] == "passed" and result["image_count"] == 1
    assert "provider.invalid" not in str(result)
