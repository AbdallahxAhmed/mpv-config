import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
MPV = r"C:\Program Files\mpv\mpv.com"

suites = [
    "test_stream_policy.lua",
    "test_ytdl_hook.lua",
    "test_player_toolbar.lua",
    "test_caption_menu.lua",
    "test_smart_paste.lua",
]

all_passed = True

for suite in suites:
    suite_path = ROOT / "tests" / "lua" / suite
    if not suite_path.exists():
        print(f"Skipping {suite}: not found")
        continue

    escaped_path = str(suite_path).replace("\\", "/")
    wrapper_content = f"""
setmetatable(_G, {{
    __newindex = function(t, k, v)
        if k == "mp" and type(v) == "table" and not v.log then
            v.log = function() end
        end
        rawset(t, k, v)
    end
}})
if mp and not mp.log then
    mp.log = function() end
end
local ok, err = pcall(function()
    dofile("{escaped_path}")
end)
if not ok then
    io.stderr:write("LUA TEST ERROR in {suite}: " .. tostring(err) .. "\\n")
    os.exit(1)
else
    os.exit(0)
end
"""
    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
        f.write(wrapper_content)
        temp_path = f.name

    try:
        proc = subprocess.run(
            [MPV, "--no-config", "--load-scripts=no", "--idle=yes", f"--script={temp_path}"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(ROOT),
        )
        if proc.returncode == 0:
            print(f"PASS: {suite}")
            # Print any ok lines from stdout
            for line in proc.stdout.splitlines():
                if "ok" in line.lower() or "passed" in line.lower():
                    print(f"  {line}")
        else:
            print(f"FAIL: {suite} (code {proc.returncode})")
            print("STDOUT:", proc.stdout)
            print("STDERR:", proc.stderr)
            all_passed = False
    except Exception as e:
        print(f"ERROR running {suite}: {e}")
        all_passed = False
    finally:
        Path(temp_path).unlink(missing_ok=True)

if not all_passed:
    sys.exit(1)
print("All Lua test suites executed successfully.")
