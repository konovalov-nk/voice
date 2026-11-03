import sys
import types

def _mkmod(name):
    m = types.ModuleType(name)
    m.__path__ = []
    m.__file__ = f'/tmp/{name.replace(".","_")}.py'
    sys.modules[name] = m
    return m

for pkg in ['nv_one_logger', 'nv_one_logger.api', 'nv_one_logger.api.config',
            'nv_one_logger.training_telemetry', 'nv_one_logger.training_telemetry.api',
            'nv_one_logger.training_telemetry.api.callbacks',
            'nv_one_logger.training_telemetry.api.config',
            'nv_one_logger.training_telemetry.api.training_telemetry_provider',
            'nv_one_logger.training_telemetry.integration',
            'nv_one_logger.training_telemetry.integration.pytorch_lightning']:
    _mkmod(pkg)

class OneLoggerConfig:
    def __init__(self, **kwargs): pass

class TrainingTelemetryConfig:
    def __init__(self, **kwargs): pass

class TrainingTelemetryProvider:
    _instance = None
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    def with_base_config(self, *a, **kw): return self
    def with_export_config(self, *a, **kw): return self
    def configure_provider(self, *a, **kw): pass
    def set_training_telemetry_config(self, *a, **kw): pass
    @property
    def config(self): return type('cfg',(),{'telemetry_config': None})()

class TimeEventCallback:
    def __init__(self, *a, **kw): pass

def on_app_start(*a, **kw): pass
def on_app_end(*a, **kw): pass

sys.modules['nv_one_logger'].OneLoggerConfig = OneLoggerConfig
sys.modules['nv_one_logger.api.config'].OneLoggerConfig = OneLoggerConfig
sys.modules['nv_one_logger.training_telemetry.api.callbacks'].on_app_start = on_app_start
sys.modules['nv_one_logger.training_telemetry.api.callbacks'].on_app_end = on_app_end
sys.modules['nv_one_logger.training_telemetry.api.config'].TrainingTelemetryConfig = TrainingTelemetryConfig
sys.modules['nv_one_logger.training_telemetry.api.training_telemetry_provider'].TrainingTelemetryProvider = TrainingTelemetryProvider
sys.modules['nv_one_logger.training_telemetry.integration.pytorch_lightning'].TimeEventCallback = TimeEventCallback
