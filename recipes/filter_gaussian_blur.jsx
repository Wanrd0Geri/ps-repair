// 配方：filter_gaussian_blur
// 用途：高斯模糊：远景虚化、柔化生硬接缝、做空气透视的底。
// 参数：
//   doc_id       int      默认=当前文档
//   radius       number   默认=2   0.1-1000 像素
//   selection    选区     默认=沿用当前选区；无选区=整层（蒙版全显）
//   layer_id / source / expand_px / feather_px / label   同 content_aware_fill
// 产出：图层「修_filter_gaussian_blur_<label>」= 源图层副本（滤镜后）+ 选区蒙版；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分。

function run(args) {
  var doc = getDoc(args);
  var r = Number(opt(args, 'radius', 2));
  if (!(r >= 0.1 && r <= 1000)) fail('BAD_ARG', 'radius 0.1-1000');
  return filterFlow(doc, args, 'filter_gaussian_blur', r * 3, function (layer) { layer.applyGaussianBlur(r); });
}
