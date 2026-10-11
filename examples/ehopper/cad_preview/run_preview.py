# Mirrors ehopper freecad_run: cwd and GUACAMOLE_SANDBOX point at this preview copy.
print("PREVIEW_RUNNER_START", flush=True)
import os
root = "/home/ngvnngkhoi/guacamole/examples/ehopper/cad_preview"
os.chdir(root)
os.environ["GUACAMOLE_SANDBOX"] = root
path = root + "/cad/pdr_r12_chief/build_braced_candidates_01.py"
exec(compile(open(path, encoding="utf-8").read(), path, "exec"), {"__name__": "__main__"})
