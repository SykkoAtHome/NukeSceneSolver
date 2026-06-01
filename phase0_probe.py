"""Phase 0 environment probe for the AI calibration plan.

Run with Nuke's bundled interpreter to learn what the AI stack can import
in-process versus what must move to a sidecar venv.
"""
import sys

print("=== interpreter ===")
print("python:", sys.version.replace("\n", " "))
print("executable:", sys.executable)

print("\n=== sys.path (third-party roots) ===")
for p in sys.path:
    if "site-packages" in p or "pythonextensions" in p:
        print(" ", p)


def probe(name, extra=None):
    try:
        mod = __import__(name)
        ver = getattr(mod, "__version__", "?")
        line = "OK   %-12s %s" % (name, ver)
        if extra:
            try:
                line += "  " + extra(mod)
            except Exception as e:  # noqa: BLE001
                line += "  [extra failed: %r]" % e
        print(line)
    except Exception as e:  # noqa: BLE001
        print("FAIL %-12s %r" % (name, e))


print("\n=== core numeric (expected present) ===")
probe("numpy")
probe("scipy")

print("\n=== AI stack ===")


def cv2_extra(cv2):
    parts = []
    try:
        cv2.createLineSegmentDetector()
        parts.append("LSD:OK")
    except Exception as e:  # noqa: BLE001
        parts.append("LSD:FAIL(%s)" % type(e).__name__)
    has_ximg = hasattr(cv2, "ximgproc")
    parts.append("ximgproc:%s" % has_ximg)
    return " ".join(parts)


def torch_extra(torch):
    return "cuda:%s" % torch.cuda.is_available()


probe("cv2", cv2_extra)
probe("torch", torch_extra)
probe("kornia")
probe("cvxpy")

print("\n=== done ===")
