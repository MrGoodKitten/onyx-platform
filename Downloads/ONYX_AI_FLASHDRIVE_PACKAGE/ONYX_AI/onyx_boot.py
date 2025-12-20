from onyx_engine.core import ONYXCore
from onyx_engine.persona import ONYXPersona
from onyx_engine.renderer import ONYXRenderer

if __name__ == '__main__':
    core = ONYXCore()
    persona = ONYXPersona()
    renderer = ONYXRenderer()

    core.boot_sequence()
    renderer.show_identity()
    persona.greet()
