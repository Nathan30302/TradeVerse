import importlib, traceback
try:
    p = importlib.import_module('app.utils.pnl_calculator')
    print('imported pnl_calculator OK')
    print('Available functions:', [k for k in dir(p) if k.startswith('calculate') or k.startswith('detect')])
except Exception:
    print('IMPORT ERROR')
    traceback.print_exc()
