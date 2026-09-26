// 配方：content_aware_fill
// 用途：内容识别填充去小瑕疵（白框、噪点块、多余小物件）。复制源图层 → 在副本的选区里填充 → 蒙版只露选区。
// 参数：
//   doc_id             int      默认=当前文档
//   selection          选区     默认="current"   {"rect"}/{"polygon"}/{"channel"}/"current"；必须有选区
//   layer_id           int      默认=当前图层    源图层（普通像素层）
//   source             str      默认="layer"     "merged"=先盖印全部可见图层再做（源图层上方还有修改层时用）
//   grow_px            int      默认=0           填充前先把选区外扩（让填充盖住瑕疵的光晕）
//   expand_px          int      默认=0           蒙版比填充区再外扩（给之后的蒙版羽化留余量）
//   feather_px         number   默认=0           蒙版羽化（可逆，mask_set 可再改）
//   color_adaptation   bool     默认=true        颜色适应
//   label              str      默认=""          图层名后缀
// 产出：图层「修_content_aware_fill_<label>」= 源图层副本 + 显示选区的蒙版；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（caf_test.jsx 真实图 + tests/run_tests.py）
// 费用/限制：本地、秒级、不扣积分；“编辑 > 填充 > 内容识别”（旧版单步，不是内容识别填充工作区），
//   不能指定取样区；大块结构（屋檐、窗格）会糊或重复纹理——那类问题回即梦局部重绘。

function run(args) {
  var doc = getDoc(args);
  applySelection(doc, opt(args, 'selection', 'current'));
  if (!hasSelection(doc)) fail('NO_SELECTION', '内容识别填充需要选区');
  var work = makeWorkLayer(doc, args, 'content_aware_fill'), fillBounds;
  try {
    targetPixels(doc);
    if (Number(opt(args, 'grow_px', 0)) > 0) doc.selection.expand(px(opt(args, 'grow_px', 0)));
    fillBounds = selBounds(doc);
    var d = new ActionDescriptor();
    d.putEnumerated(sTID('using'), sTID('fillContents'), sTID('contentAware'));
    d.putBoolean(sTID('contentAwareColorAdaptationFill'), !!opt(args, 'color_adaptation', true));
    d.putUnitDouble(sTID('opacity'), sTID('percentUnit'), 100);
    d.putEnumerated(sTID('mode'), sTID('blendMode'), sTID('normal'));
    executeAction(sTID('fill'), d, DialogModes.NO);
    maskFromSelection(doc, work, true, opt(args, 'expand_px', 0));
  } catch (e) {
    discardLayer(work);  // 失败不留半成品图层
    throw e;
  }
  var info = finishLayer(doc, work, args);
  info.fill_bounds = fillBounds;
  return info;
}
