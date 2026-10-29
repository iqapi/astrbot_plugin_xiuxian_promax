import sys, types
sys.modules.setdefault('astrbot', types.ModuleType('astrbot'))
api = types.ModuleType('astrbot.api')
api.logger = types.SimpleNamespace(info=lambda *a: None, warning=lambda *a: None, error=lambda *a: None, exception=lambda *a: None)
sys.modules['astrbot.api'] = api
sys.path.insert(0, '.')
from PIL import Image
import utils.image_generator as ig
img = Image.new('RGBA', (400, 120), (30, 26, 20, 255))
ig._gold_gradient_text(img, (10, 10), '签到成功', ig._load_font(28, 'heavy'))
ig._draw_mixed(img, (10, 60), '⚔️ 战斗 100 段', ig._load_font(20, 'text'), 18, (242, 232, 214))
img.save('_render_test.png')
print('RENDER OK')
