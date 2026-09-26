// 配方：mask_from_selection
// 用途：给已有的“修_”图层按选区建（或重建）蒙版，例如换一个更准的选区重新限定修补范围。
// 参数：
//   doc_id            int      默认=当前文档
//   layer_id          int      默认=当前图层
//   selection         选区     默认="current"
//   mode              str      默认="reveal"   reveal=只露选区，hide=隐藏选区
//   expand_px         int      默认=0
//   feather_px        number   默认=0
//   replace           bool     默认=false      图层已有蒙版时 true=删掉旧蒙版重建，false=报错
//   allow_any_layer   bool     默认=false      默认只改名字以“修_”开头的图层
// 产出：该图层的新蒙版；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；背景层不能加蒙版（报错）。

function run(args) {
  var doc = getDoc(args);
  var layer = sourceLayer(doc, args);
  assertOwnLayer(layer, args);
  if (layer.typename == 'ArtLayer' && layer.isBackgroundLayer) fail('BAD_TARGET', '背景层不能加蒙版');
  var how = { reveal: 'RvlS', hide: 'HdSl' }[opt(args, 'mode', 'reveal')];
  if (!how) fail('BAD_ARG', 'mode 只能是 reveal/hide');
  var hadMask = maskState(layer.id).has_mask;
  if (hadMask && !opt(args, 'replace', false)) fail('MASK_EXISTS', '图层已有蒙版；重建请传 replace:true');
  applySelection(doc, opt(args, 'selection', 'current'));
  if (!hasSelection(doc)) fail('NO_SELECTION', '需要选区');
  doc.activeLayer = layer;
  if (hadMask) {
    var d = new ActionDescriptor(); var r = new ActionReference();
    r.putEnumerated(cTID('Chnl'), cTID('Chnl'), cTID('Msk '));
    d.putReference(cTID('null'), r);
    executeAction(cTID('Dlt '), d, DialogModes.NO);
  }
  expandSelection(doc, opt(args, 'expand_px', 0));
  makeMask(how);
  return finishLayer(doc, layer, args);
}
