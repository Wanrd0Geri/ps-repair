// 配方：filter_lens_blur
// 用途：镜头模糊（旧版“滤镜 > 模糊 > 镜头模糊”，事件 Bokh）：给远景/背景做带光圈形状的虚化，比高斯模糊更像真实景深。
// 参数：
//   doc_id              int      默认=当前文档
//   radius              number   默认=10     光圈半径 0-100
//   blade_curvature     int      默认=0      0-100
//   rotation            int      默认=0      0-360
//   iris                str      默认="hexagon"   triangle/square/pentagon/hexagon/heptagon/octagon
//   specular_brightness number   默认=0      0-100（镜面高光亮度）
//   specular_threshold  int      默认=255    0-255
//   noise               int      默认=0      0-100（补回颗粒）
//   selection           选区     默认=沿用当前选区；无选区=整层（蒙版全显）
//   layer_id / source / expand_px / feather_px / label   同 content_aware_fill
// 产出：图层「修_filter_lens_blur_<label>」= 源图层副本（镜头模糊后）+ 选区蒙版；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py：蒙版区内变化、区外逐位不变）。描述符按插件自带
//   PiPLs.json 术语表写（BkDi/BkIs/BkIb/BkIc/BkIr/BkSb/BkSt/BkNa/BkNt/BkNm）；iris 以外的形状参数未逐个验证。
// 费用/限制：本地、不扣积分；不用深度图（BkDi=None，均匀模糊），要景深渐变请配合渐变蒙版；大半径较慢。

var IRIS = { triangle: 'BeS3', square: 'BeS4', pentagon: 'BeS5', hexagon: 'BeS6', heptagon: 'BeS7', octagon: 'BeS8' };

function run(args) {
  var doc = getDoc(args);
  var r = Number(opt(args, 'radius', 10));
  var iris = IRIS[opt(args, 'iris', 'hexagon')];
  if (!iris || !(r >= 0 && r <= 100)) fail('BAD_ARG', 'radius 0-100，iris 取值见说明');
  return filterFlow(doc, args, 'filter_lens_blur', r * 2, function () {
    var d = new ActionDescriptor();
    d.putEnumerated(cTID('BkDi'), cTID('BtDi'), cTID('BeIn'));
    d.putInteger(cTID('BkDp'), 0);
    d.putBoolean(cTID('BkDs'), false);
    d.putEnumerated(cTID('BkIs'), cTID('BtIs'), cTID(iris));
    d.putDouble(cTID('BkIb'), r);
    d.putInteger(cTID('BkIc'), Math.round(Number(opt(args, 'blade_curvature', 0))));
    d.putInteger(cTID('BkIr'), Math.round(Number(opt(args, 'rotation', 0))));
    d.putDouble(cTID('BkSb'), Number(opt(args, 'specular_brightness', 0)));
    d.putInteger(cTID('BkSt'), Math.round(Number(opt(args, 'specular_threshold', 255))));
    d.putInteger(cTID('BkNa'), Math.round(Number(opt(args, 'noise', 0))));
    d.putEnumerated(cTID('BkNt'), cTID('BtNt'), cTID('BeNu'));
    d.putBoolean(cTID('BkNm'), true);
    executeAction(cTID('Bokh'), d, DialogModes.NO);
  });
}
