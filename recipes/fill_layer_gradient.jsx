// 配方：fill_layer_gradient
// 用途：渐变填充层（带蒙版）：给天空补过渡、做远景空气透视的雾（上浓下淡）、压暗角落。
// 参数：
//   doc_id         int        默认=当前文档
//   from_rgb       [r,g,b]    必填   起点颜色（0-255）
//   to_rgb         [r,g,b]    默认=from_rgb
//   from_opacity   number     默认=100   起点不透明度 %
//   to_opacity     number     默认=0     终点不透明度 %
//   angle          number     默认=90    角度（90=从下到上：起点在下）
//   type           str        默认="linear"   linear/radial
//   scale          number     默认=100   缩放 %
//   dither         bool       默认=true  仿色（防色带）
//   opacity        number     默认=100   图层不透明度
//   blend          str        默认="normal"
//   selection / layer_id / expand_px / feather_px / clip / label   同 fill_layer_solid
// 产出：图层「修_fill_layer_gradient_<label>」（渐变填充层 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py，linear）；type=radial 未单独验证。
// 费用/限制：本地、不扣积分；渐变“与图层对齐”（有选区时按蒙版外接框铺渐变）。

function stopColor(rgb, loc) {
  var s = new ActionDescriptor();
  s.putObject(cTID('Clr '), cTID('RGBC'), rgbDesc(rgb));
  s.putEnumerated(cTID('Type'), cTID('Clry'), cTID('UsrS'));
  s.putInteger(cTID('Lctn'), loc); s.putInteger(cTID('Mdpn'), 50);
  return s;
}
function stopAlpha(op, loc) {
  var t = new ActionDescriptor();
  t.putUnitDouble(cTID('Opct'), cTID('#Prc'), Number(op));
  t.putInteger(cTID('Lctn'), loc); t.putInteger(cTID('Mdpn'), 50);
  return t;
}

function run(args) {
  var doc = getDoc(args);
  var from = opt(args, 'from_rgb', null), to = opt(args, 'to_rgb', from);
  var type = { linear: 'Lnr ', radial: 'Rdl ' }[opt(args, 'type', 'linear')];
  if (!type) fail('BAD_ARG', 'type 只能是 linear/radial');
  var mode = blendMode(opt(args, 'blend', 'normal'));
  var g = new ActionDescriptor();
  g.putString(cTID('Nm  '), 'ps-repair');
  g.putEnumerated(cTID('GrdF'), cTID('GrdF'), cTID('CstS'));
  g.putDouble(cTID('Intr'), 4096);
  var clrs = new ActionList();
  clrs.putObject(cTID('Clrt'), stopColor(from, 0)); clrs.putObject(cTID('Clrt'), stopColor(to, 4096));
  g.putList(cTID('Clrs'), clrs);
  var tr = new ActionList();
  tr.putObject(cTID('TrnS'), stopAlpha(opt(args, 'from_opacity', 100), 0));
  tr.putObject(cTID('TrnS'), stopAlpha(opt(args, 'to_opacity', 0), 4096));
  g.putList(cTID('Trns'), tr);
  var c = new ActionDescriptor();
  c.putBoolean(cTID('Dthr'), !!opt(args, 'dither', true));
  c.putUnitDouble(cTID('Angl'), cTID('#Ang'), Number(opt(args, 'angle', 90)));
  c.putEnumerated(cTID('Type'), cTID('GrdT'), cTID(type));
  c.putBoolean(cTID('Algn'), true);
  c.putUnitDouble(cTID('Scl '), cTID('#Prc'), Number(opt(args, 'scale', 100)));
  c.putObject(cTID('Grad'), cTID('Grdn'), g);
  var info = adjustmentFlow(doc, args, 'fill_layer_gradient', function () { return makeFillLayer(sTID('gradientLayer'), c); });
  var layer = findLayer(doc, info.id);
  layer.opacity = Number(opt(args, 'opacity', 100));
  layer.blendMode = mode;
  var out = layerInfo(layer);
  out.used_selection = info.used_selection;
  return out;
}
