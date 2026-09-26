// 配方：filter_surface_blur
// 用途：表面模糊（保边磨平）：天空色带、墙面、水面的斑驳与块状噪声，比特殊模糊更柔。
// 参数：
//   doc_id       int      默认=当前文档
//   radius       number   默认=5     1-100 像素
//   threshold    int      默认=15    2-255 色阶，越小越保边
//   selection    选区     默认=沿用当前选区；无选区=整层（蒙版全显）
//   layer_id / source / expand_px / feather_px / label   同 content_aware_fill
// 产出：图层「修_filter_surface_blur_<label>」= 源图层副本（滤镜后）+ 选区蒙版；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；半径大时较慢（只在蒙版外接框 + 余量内计算）。

function run(args) {
  var doc = getDoc(args);
  var r = Number(opt(args, 'radius', 5)), t = Math.round(Number(opt(args, 'threshold', 15)));
  if (!(r >= 1 && r <= 100 && t >= 2 && t <= 255)) fail('BAD_ARG', 'radius 1-100，threshold 2-255');
  return filterFlow(doc, args, 'filter_surface_blur', r * 3, function () {
    var d = new ActionDescriptor();
    d.putUnitDouble(cTID('Rds '), cTID('#Pxl'), r);
    d.putInteger(cTID('Thsh'), t);
    executeAction(sTID('surfaceBlur'), d, DialogModes.NO);
  });
}
