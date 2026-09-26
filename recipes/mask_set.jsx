// 配方：mask_set
// 用途：改图层蒙版属性（都可逆）：羽化、浓度、停用/启用，或把蒙版反相。
// 参数：
//   doc_id            int      默认=当前文档
//   layer_id          int      默认=当前图层
//   feather_px        number   可选   蒙版羽化 0-1000 像素（属性面板“羽化”，不改蒙版像素）
//   density           number   可选   蒙版浓度 0-100（%）
//   enabled           bool     可选   false=停用蒙版（看整层效果），true=启用
//   invert            bool     可选   true=反相蒙版像素（会写进蒙版，不是属性）
//   allow_any_layer   bool     默认=false   默认只改名字以“修_”开头的图层
// 产出：无新图层；返回读回的蒙版状态 {has_mask, enabled, density(%), feather}
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；图层必须已有蒙版。

function run(args) {
  var doc = getDoc(args);
  var layer = sourceLayer(doc, args);
  assertOwnLayer(layer, args);
  if (!maskState(layer.id).has_mask) fail('NO_MASK', '图层「' + layer.name + '」没有蒙版');
  var dens = opt(args, 'density', null);
  if (dens !== null && !(dens >= 0 && dens <= 100)) fail('BAD_ARG', 'density 0-100');
  setMaskProps(layer.id, { feather: opt(args, 'feather_px', null), density: dens, enabled: opt(args, 'enabled', null) });
  if (opt(args, 'invert', false)) {
    doc.activeLayer = layer;
    var d = new ActionDescriptor(); var r = new ActionReference();
    r.putEnumerated(cTID('Chnl'), cTID('Chnl'), cTID('Msk '));
    d.putReference(cTID('null'), r); d.putBoolean(cTID('MkVs'), false);
    executeAction(cTID('slct'), d, DialogModes.NO);
    executeAction(cTID('Invr'), undefined, DialogModes.NO);
    try { targetPixels(doc); } catch (e) {}  // 调整层没有像素通道，忽略
  }
  var info = layerInfo(layer);
  return info;
}
