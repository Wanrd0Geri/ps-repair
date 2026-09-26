// 配方：duplicate_doc
// 用途：复制文档做试做（在副本上试方法，满意后再在正式文档上只加图层）。
// 参数：
//   doc_id   int    默认=当前文档
//   name     str    默认="试做_<原名>"   副本名；不以“试做_”开头时自动加前缀（close_doc 靠这个前缀识别试做文档）
//   merge    bool   默认=false          true=只保留合并后的单层（= duplicate(名, true)“仅复制合并的图层”）
// 产出：新文档（成为当前文档），返回其 doc_id
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；大图副本占内存。注意 merge:true 会把当时所有可见图层（含半透明雾层等修改层）
//   烧进像素——FINDINGS 里误判的“44 dB 漂移”就是这么来的；做验收对比时保持默认 false。

function run(args) {
  var src = getDoc(args);
  var name = opt(args, 'name', src.name.replace(/\.[^.]+$/, ''));
  if (name.indexOf(TRIAL_PREFIX) != 0) name = TRIAL_PREFIX + name;
  var dup = src.duplicate(name, !!opt(args, 'merge', false));
  app.activeDocument = dup;
  __TARGET_DOC = dup;
  var info = docInfo(dup);
  info.source_doc_id = src.id;
  info.layer_count = dup.layers.length;
  return info;
}
