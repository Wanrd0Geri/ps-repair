// 配方：filter_add_noise
// 用途：添加杂色：给填充/模糊过的区域补回颗粒，让修补处和周围 AI 图的噪点质感一致。
// 参数：
//   doc_id          int      默认=当前文档
//   amount          number   默认=2      0.1-400（%）
//   distribution    str      默认="gaussian"   gaussian/uniform
//   monochromatic   bool     默认=true
//   selection       选区     默认=沿用当前选区；无选区=整层（蒙版全显）
//   layer_id / source / expand_px / feather_px / label   同 content_aware_fill
// 产出：图层「修_filter_add_noise_<label>」= 源图层副本（加杂色后）+ 选区蒙版；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；杂色随机，每次结果不同。

function run(args) {
  var doc = getDoc(args);
  var a = Number(opt(args, 'amount', 2));
  var dist = { gaussian: 'GAUSSIAN', uniform: 'UNIFORM' }[opt(args, 'distribution', 'gaussian')];
  if (!dist || !(a >= 0.1 && a <= 400)) fail('BAD_ARG', 'amount 0.1-400，distribution gaussian/uniform');
  return filterFlow(doc, args, 'filter_add_noise', 2, function (layer) {
    layer.applyAddNoise(a, NoiseDistribution[dist], !!opt(args, 'monochromatic', true));
  });
}
