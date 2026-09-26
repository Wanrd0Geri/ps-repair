// 配方：fill_layer_solid
// 用途：纯色填充层（带蒙版），用于压暗/提亮/偏色修正（配合混合模式与不透明度），或补一块平色底。
// 参数：
//   doc_id       int        默认=当前文档
//   rgb          [r,g,b]    必填   0-255
//   selection    选区       默认=沿用当前选区；无选区=全图
//   layer_id     int        默认=当前图层   新层插在它上方
//   expand_px    int        默认=0
//   feather_px   number     默认=0
//   opacity      number     默认=100
//   blend        str        默认="normal"   如 multiply/screen/overlay/soft_light/color/luminosity
//   clip         bool       默认=false      剪贴到下方图层
//   label        str        默认=""
// 产出：图层「修_fill_layer_solid_<label>」（纯色填充层 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分。

function run(args) {
  var doc = getDoc(args);
  var s = new ActionDescriptor();
  s.putObject(cTID('Clr '), cTID('RGBC'), rgbDesc(opt(args, 'rgb', null)));  // 先校验参数再动文档
  var mode = blendMode(opt(args, 'blend', 'normal'));
  var info = adjustmentFlow(doc, args, 'fill_layer_solid', function () {
    return makeFillLayer(sTID('solidColorLayer'), s);
  });
  var layer = findLayer(doc, info.id);
  layer.opacity = Number(opt(args, 'opacity', 100));
  layer.blendMode = mode;
  var out = layerInfo(layer);
  out.used_selection = info.used_selection;
  return out;
}
