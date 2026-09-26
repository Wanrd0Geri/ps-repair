// 测试用：新建合成文档（不碰任何已打开文档）。由 run_tests.py 通过 psrun.py --jsx 调用。
// 画面（800×600 默认）：上 250px 蓝色渐变“天空”，下面黄绿“地面”，红方块 [500,300,640,440]，
// 黄圆（圆心 200,420 半径 60），天空里一个白色小方框瑕疵 [350,150,390,190]（线宽 3），全图单色杂色 3%。
// 参数：name（默认“试做_ps_repair_test”）、width、height、extra_layer（true 时再加一个名为“上层”的普通图层）。

function fillRect(doc, r, rgb) {
  doc.selection.select(rectPoints(r), SelectionType.REPLACE, 0, false);
  var c = new SolidColor(); c.rgb.red = rgb[0]; c.rgb.green = rgb[1]; c.rgb.blue = rgb[2];
  doc.selection.fill(c);
}
function circlePoints(cx, cy, r, n) {
  var pts = [];
  for (var i = 0; i < n; i++) { var a = 2 * Math.PI * i / n; pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]); }
  return pts;
}

function run(args) {
  var w = opt(args, 'width', 800), h = opt(args, 'height', 600);
  var name = opt(args, 'name', TRIAL_PREFIX + 'ps_repair_test');
  var doc = app.documents.add(w, h, 72, name, NewDocumentMode.RGB, DocumentFill.WHITE, 1.0,
                              BitsPerChannelType.EIGHT, 'sRGB IEC61966-2.1');
  __TARGET_DOC = doc;
  var sky = [[70, 115, 190], [85, 130, 200], [100, 145, 210], [120, 160, 220], [140, 178, 228], [160, 195, 235]];
  for (var i = 0; i < sky.length; i++) fillRect(doc, [0, i * 42, w, Math.min(250, (i + 1) * 42 + 1)], sky[i]);
  doc.selection.select(rectPoints([0, 0, w, 250]), SelectionType.REPLACE, 0, false);
  doc.activeLayer.applyGaussianBlur(12);
  fillRect(doc, [0, 250, w, h], [120, 140, 70]);
  fillRect(doc, [500, 300, 640, 440], [200, 40, 40]);
  doc.selection.select(circlePoints(200, 420, 60, 48), SelectionType.REPLACE, 0, true);
  var y = new SolidColor(); y.rgb.red = 230; y.rgb.green = 200; y.rgb.blue = 40; doc.selection.fill(y);
  doc.selection.select(rectPoints([350, 150, 390, 190]), SelectionType.REPLACE, 0, false);
  doc.selection.select(rectPoints([353, 153, 387, 187]), SelectionType.DIMINISH, 0, false);
  var wht = new SolidColor(); wht.rgb.red = 255; wht.rgb.green = 255; wht.rgb.blue = 255; doc.selection.fill(wht);
  doc.selection.deselect();
  doc.activeLayer.applyAddNoise(3, NoiseDistribution.GAUSSIAN, true);
  doc.flatten();
  if (opt(args, 'extra_layer', false)) {
    var top = doc.artLayers.add();
    top.name = '上层';  // “上层”
    fillRect(doc, [80, 60, 300, 200], [250, 120, 30]);
    doc.selection.deselect();
    top.opacity = 60;
    top.blendMode = BlendMode.OVERLAY;
  }
  var info = docInfo(doc);
  info.layers = [];
  for (var k = 0; k < doc.layers.length; k++) info.layers.push(layerInfo(doc.layers[k]));
  return info;
}
