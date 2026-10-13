"""Replace unsafe runtime authentication defaults without disclosing app settings."""
import ast
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile


SECRET_NAMES = ("JWT_SECRET_KEY", "CSRF_SECRET_KEY")


def azure_json(*arguments):
    result = subprocess.run(
        ["az", *arguments, "--output", "json", "--only-show-errors"],
        capture_output=True, text=True,
    )
    if result.returncode:
        # CLI diagnostics may contain settings: report only the failed operation.
        raise RuntimeError("Azure configuration operation failed; check the workflow identity's app permissions")
    return json.loads(result.stdout)


def repair(app_name, resource_group):
    source = ast.parse(Path("app/core/config.py").read_text(encoding="utf-8-sig"))
    settings_class = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "Settings")
    defaults = {
        node.target.id: ast.literal_eval(node.value)
        for node in settings_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        and node.target.id in SECRET_NAMES
    }
    target = ["--name", app_name, "--resource-group", resource_group]
    current = {row["name"]: row["value"] for row in azure_json("webapp", "config", "appsettings", "list", *target)}
    updates = {}
    for name in SECRET_NAMES:
        value = current.get(name) or ""
        if value == defaults[name] or len(value.strip()) < 32:
            updates[name] = secrets.token_urlsafe(48)
    if updates.get("JWT_SECRET_KEY", current.get("JWT_SECRET_KEY")) == updates.get("CSRF_SECRET_KEY", current.get("CSRF_SECRET_KEY")):
        updates["CSRF_SECRET_KEY"] = secrets.token_urlsafe(48)
    if str(current.get("COOKIE_SECURE", "")).strip().lower() != "true":
        updates["COOKIE_SECURE"] = "true"

    if updates:
        # Azure CLI reads JSON from a private runner file, avoiding secret arguments.
        path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
                path = handle.name
                os.chmod(path, 0o600)
                json.dump(updates, handle)
            result = subprocess.run(
                ["az", "webapp", "config", "appsettings", "set", *target,
                 "--settings", "@" + path, "--output", "none", "--only-show-errors"],
                capture_output=True, text=True,
            )
            if result.returncode:
                raise RuntimeError("Azure runtime settings update failed")
        finally:
            if path is not None:
                Path(path).unlink(missing_ok=True)
        verified = {row["name"]: row["value"] for row in azure_json("webapp", "config", "appsettings", "list", *target)}
        if any(verified.get(name) != value for name, value in updates.items()):
            raise RuntimeError("Azure runtime settings did not match the repair")
        print("Updated runtime settings: " + ", ".join(sorted(updates)))
    else:
        print("Runtime authentication settings already satisfy production validation")
    result = subprocess.run(
        ["az", "webapp", "restart", *target, "--output", "none", "--only-show-errors"],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError("Runtime settings checked, but the app restart failed")
    print("Backend restart requested")


if __name__ == "__main__":
    repair("catms-backedn", "catms-backedn_group")
