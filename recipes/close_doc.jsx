// 配方：close_doc
// 用途：关闭试做文档，永远“不保存”。
// 参数：
//   doc_id   int    必填（不接受默认当前文档，防止误关用户文档）
//   force    bool   默认=false   默认只关名字以“试做_”开头的文档；关别的文档必须 force:true
// 产出：无；返回关闭后的当前文档 id
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：关闭即丢弃未保存修改，不可撤销——只用于试做文档。

function run(args) {
  if (args.doc_id === undefined || args.doc_id === null) fail('BAD_ARG', 'close_doc 必须显式给 doc_id');
  var doc = findDoc(args.doc_id);
  if (!doc) fail('DOC_NOT_FOUND', 'doc_id=' + args.doc_id);
  if (!isTrialDoc(doc) && !opt(args, 'force', false))
    fail('PROTECTED_DOC', '「' + doc.name + '」不是“试做_”文档；确需关闭（不保存）请传 force:true');
  var name = doc.name;
  doc.close(SaveOptions.DONOTSAVECHANGES);
  var active = null;
  try { active = app.activeDocument.id; } catch (e) {}
  return { closed_doc_id: args.doc_id, closed_name: name, active_doc_id: active };
}
