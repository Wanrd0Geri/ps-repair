// 配方：select_modify
// 用途：修改当前选区：羽化 / 扩展 / 收缩 / 平滑 / 反选 / 取消 / 全选。
// 参数：
//   doc_id   int      默认=当前文档
//   op       str      feather|expand|contract|smooth|invert|deselect|all（与 ops 二选一）
//   px       number   feather/expand/contract/smooth 的像素值
//   ops      list     依次执行多步，如 [{"op":"expand","px":4},{"op":"feather","px":2}]
// 产出：选区；返回 bounds（取消选区后为 null）
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；expand/contract 单次上限 500 px（PS 限制），扩展会把直角变圆角。

function modifyOnce(doc, op, n) {
  if (op == 'deselect') { doc.selection.deselect(); return; }
  if (op == 'all') { doc.selection.selectAll(); return; }
  if (!hasSelection(doc)) fail('NO_SELECTION', op + ' 需要已有选区');
  if (op == 'invert') { doc.selection.invert(); return; }
  if (!(Number(n) > 0)) fail('BAD_ARG', op + ' 需要 px > 0');
  if (op == 'feather') doc.selection.feather(px(n));
  else if (op == 'expand') doc.selection.expand(px(n));
  else if (op == 'contract') doc.selection.contract(px(n));
  else if (op == 'smooth') doc.selection.smooth(Number(n));
  else fail('BAD_ARG', '未知 op：' + op);
}

function run(args) {
  var doc = getDoc(args);
  var ops = opt(args, 'ops', null) || [{ op: opt(args, 'op', ''), px: opt(args, 'px', 0) }];
  for (var i = 0; i < ops.length; i++) modifyOnce(doc, ops[i].op, ops[i].px);
  return { bounds: selBounds(doc), steps: ops.length };
}
