"""
ot_collab/ot_engine.py
----------------------
Pure operational transformation logic.

Zero I/O. Zero side effects. Every function is a pure transformation
of its inputs. This entire file can be tested with plain assertions,
no database, no Redis, no WebSocket.

The four core functions:

  transform(op_a, op_b) → op_a'
    Given that op_b has already been applied to the document,
    adjust op_a so its original intent is preserved.
    This is the mathematical heart of OT.

  transform_against_many(op, ops) → op'
    Sequential transform of op against a list of already-applied ops.
    Used for catchup: client sent at revision 5, server is at 8,
    transform against history[5:8].

  apply(content, op) → str
    Apply op to a content string. Returns the new string.
    Used server-side to update the document in Redis.

  compose(op_a, op_b) → op'
    Merge two sequential ops into one equivalent op.
    op_b must have been generated on the result of applying op_a.
    Used client-side to compress pending_queue before sending.

Database analogy recap:
  transform()              ≈ MVCC conflict resolution (rebase instead of abort)
  transform_against_many() ≈ replaying missed commits onto a stale snapshot
  apply()                  ≈ committing a transaction to the document
  compose()                ≈ batching writes into a single transaction
"""

from __future__ import annotations
from .models import Op, OpType, NoOp


# ── apply ─────────────────────────────────────────────────────────────────────

def apply(content: str, op: Op) -> str:
    """
    Apply op to content. Returns the new string.

    Raises ValueError if the op is out of bounds.
    The server should never receive an out-of-bounds op if clients are
    well-behaved, but we validate anyway — fail loudly rather than silently
    corrupt the document.
    """
    doc_len = len(content)

    if op.op_type == OpType.INSERT:
        if op.position < 0 or op.position > doc_len:
            raise ValueError(
                f"Insert position {op.position} out of bounds for doc length {doc_len}"
            )
        return content[:op.position] + op.chars + content[op.position:]

    elif op.op_type == OpType.DELETE:
        if op.position < 0 or op.position >= doc_len:
            raise ValueError(
                f"Delete position {op.position} out of bounds for doc length {doc_len}"
            )
        end = op.position + op.length
        if end > doc_len:
            raise ValueError(
                f"Delete end {end} out of bounds for doc length {doc_len}"
            )
        return content[:op.position] + content[end:]

    raise ValueError(f"Unknown op_type: {op.op_type}")


# ── transform ─────────────────────────────────────────────────────────────────

def transform(op_a: Op, op_b: Op) -> Op | NoOp:
    """
    Transform op_a against op_b.

    Precondition: op_b has already been applied to the document.
    Postcondition: applying the returned op_a' to the document that
                   already has op_b applied produces the same result as
                   applying op_a to the original document (TP1 property).

    Returns NoOp when op_a is completely nullified by op_b
    (e.g. both ops delete the exact same range).

    The four cases — visualized on a number line:

    Case 1: Insert vs Insert
      op_b inserts N chars at pos P.
      If op_a inserts at pos >= P, shift op_a right by N.
      If op_a inserts at pos <  P, no change.
      Tie (same pos): tie-break deterministically — op_a always shifts right.
      This tie-break must be symmetric: both clients apply the same rule.

    Case 2: Insert vs Delete
      op_b deletes N chars starting at pos P (range [P, P+N)).
      If op_a inserts at pos > P+N,  shift op_a left by N (gap removed).
      If op_a inserts at pos <= P,   no change.
      If op_a inserts inside [P, P+N): collapse to pos P (deleted zone).

    Case 3: Delete vs Insert
      op_b inserts N chars at pos P.
      If op_a deletes range starting after P, shift right by N.
      If op_a deletes range ending before or at P, no change.
      If op_a straddles P: expand length by N (insertion falls inside delete).

    Case 4: Delete vs Delete
      op_b deletes range B = [pb, pb + lb).
      op_a deletes range A = [pa, pa + la).
      Four sub-cases based on overlap:
        No overlap, A before B: no change.
        No overlap, A after B:  shift A left by lb.
        Partial overlap:        trim A to remove the already-deleted chars.
        Full containment:       A is fully inside B → NoOp.
    """
    dispatch = {
        (OpType.INSERT, OpType.INSERT): _transform_ins_ins,
        (OpType.INSERT, OpType.DELETE): _transform_ins_del,
        (OpType.DELETE, OpType.INSERT): _transform_del_ins,
        (OpType.DELETE, OpType.DELETE): _transform_del_del,
    }
    key = (op_a.op_type, op_b.op_type)
    fn  = dispatch.get(key)
    if fn is None:
        raise ValueError(f"Unhandled transform case: {key}")
    return fn(op_a, op_b)


def _transform_ins_ins(op_a: Op, op_b: Op) -> Op:
    """
    Transform Insert(op_a) against Insert(op_b).

    op_b inserted len(op_b.chars) chars at op_b.position.
    Adjust op_a.position accordingly.
    """
    pa = op_a.position
    pb = op_b.position
    nb = len(op_b.chars)  # number of chars op_b inserted

    # Tie-break: if positions equal, op_a shifts right.
    # This means op_b's text ends up before op_a's text.
    # Both clients must agree on this rule (symmetric).
    if pa >= pb:
        return Op(op_type=OpType.INSERT, position=pa + nb, chars=op_a.chars)
    else:
        return Op(op_type=OpType.INSERT, position=pa, chars=op_a.chars)


def _transform_ins_del(op_a: Op, op_b: Op) -> Op:
    """
    Transform Insert(op_a) against Delete(op_b).

    op_b deleted op_b.length chars starting at op_b.position.
    The gap [pb, pb+lb) no longer exists.
    """
    pa = op_a.position
    pb = op_b.position
    lb = op_b.length

    if pa <= pb:
        # op_a inserts before the deleted zone — no position change
        return Op(op_type=OpType.INSERT, position=pa, chars=op_a.chars)
    elif pa > pb + lb:
        # op_a inserts after the deleted zone — shift left by lb
        return Op(op_type=OpType.INSERT, position=pa - lb, chars=op_a.chars)
    else:
        # op_a inserts inside the deleted zone [pb, pb+lb)
        # The zone is gone, so collapse to the start of the zone
        return Op(op_type=OpType.INSERT, position=pb, chars=op_a.chars)


def _transform_del_ins(op_a: Op, op_b: Op) -> Op:
    """
    Transform Delete(op_a) against Insert(op_b).

    op_b inserted nb chars at pb.
    The document grew. Adjust op_a's range.

    If the insertion falls inside op_a's delete range,
    we expand the delete to also cover the inserted chars.
    This preserves the intent: "delete this region",
    which now includes the newly inserted text in the middle.

    This is a policy decision. The alternative (stop the delete at pb)
    is also defensible, but expanding is more intuitive for code editing.
    """
    pa = op_a.position
    la = op_a.length
    pb = op_b.position
    nb = len(op_b.chars)

    if pb <= pa:
        # insertion is before or at delete start — shift delete right
        return Op(op_type=OpType.DELETE, position=pa + nb, length=la)
    elif pb >= pa + la:
        # insertion is after delete range — no change
        return Op(op_type=OpType.DELETE, position=pa, length=la)
    else:
        # insertion falls inside the delete range
        # expand the delete to include the inserted chars
        return Op(op_type=OpType.DELETE, position=pa, length=la + nb)


def _transform_del_del(op_a: Op, op_b: Op) -> Op | NoOp:
    """
    Transform Delete(op_a) against Delete(op_b).

    This is the most complex case because ranges can overlap.

    op_a wants to delete range A = [pa, pa+la)
    op_b already deleted range B = [pb, pb+lb)

    The chars in B are already gone from the document.
    We must adjust A to only delete chars that still exist.

    Six geometric configurations on the number line:

      1. A entirely before B  (pa+la <= pb):
         No overlap. B is to the right of A. No change to A.

      2. A entirely after B  (pa >= pb+lb):
         No overlap. B is to the left of A. Shift A left by lb.

      3. A starts before B, ends inside B  (pa < pb AND pa+la > pb AND pa+la <= pb+lb):
         Partial overlap on the right side of A.
         Trim A to [pa, pb) — stop where B starts.
         New length = pb - pa.

      4. A starts inside B, ends after B  (pa >= pb AND pa+la > pb+lb):
         Partial overlap on the left side of A.
         Trim A to [pb+lb, pa+la) shifted by lb.
         New position = pb (start of where B was).
         New length = (pa + la) - (pb + lb).

      5. A entirely inside B  (pa >= pb AND pa+la <= pb+lb):
         A is completely covered by B. All chars already deleted.
         Return NoOp.

      6. B entirely inside A  (pa < pb AND pa+la > pb+lb):
         A straddles B from both sides. B chars already gone.
         New length = la - lb.
         Position stays at pa.
    """
    pa, la = op_a.position, op_a.length
    pb, lb = op_b.position, op_b.length

    a_end = pa + la
    b_end = pb + lb

    # Case 1: A entirely before B
    if a_end <= pb:
        return Op(op_type=OpType.DELETE, position=pa, length=la)

    # Case 2: A entirely after B
    if pa >= b_end:
        return Op(op_type=OpType.DELETE, position=pa - lb, length=la)

    # Case 5: A entirely inside B
    if pa >= pb and a_end <= b_end:
        return NoOp()

    # Case 6: B entirely inside A
    if pa < pb and a_end > b_end:
        new_length = la - lb
        if new_length <= 0:
            return NoOp()
        return Op(op_type=OpType.DELETE, position=pa, length=new_length)

    # Case 3: A starts before B, ends inside B
    if pa < pb and a_end > pb and a_end <= b_end:
        new_length = pb - pa
        if new_length <= 0:
            return NoOp()
        return Op(op_type=OpType.DELETE, position=pa, length=new_length)

    # Case 4: A starts inside B, ends after B
    if pa >= pb and pa < b_end and a_end > b_end:
        new_length = a_end - b_end
        if new_length <= 0:
            return NoOp()
        # Position shifts to where B ended (which is now at pb in the new doc)
        return Op(op_type=OpType.DELETE, position=pb, length=new_length)

    # Should be unreachable
    raise ValueError(
        f"Unhandled Del/Del geometry: A=[{pa},{a_end}) B=[{pb},{b_end})"
    )


# ── transform_against_many ────────────────────────────────────────────────────

def transform_against_many(op: Op, history: list[Op]) -> Op | NoOp:
    """
    Transform op sequentially against a list of already-applied ops.

    Used for catchup on the server:
      client sent op at client_revision=5, server is at revision=8.
      history = ops at revisions 6, 7, 8  (in order).
      We transform op against each, left to right.

    If at any point the op becomes a NoOp (fully cancelled), we stop early
    and return NoOp — no point continuing the transform chain.

    This is equivalent to replaying missed committed transactions
    and rebasing the pending transaction on top of each one.
    """
    current: Op | NoOp = op
    for h_op in history:
        if isinstance(current, NoOp):
            return NoOp()
        current = transform(current, h_op)
    return current


# ── compose ───────────────────────────────────────────────────────────────────

def compose(op_a: Op, op_b: Op) -> Op | None:
    """
    Compose two sequential ops into one equivalent op.
    op_b was generated on the document that results from applying op_a.

    Only handles the common cases that occur in real typing:
      - Insert followed by Insert at adjacent position (fast typing)
      - Delete followed by Delete at same or adjacent position

    Returns None if the ops cannot be composed (non-adjacent, mixed types).
    Caller falls back to sending them as separate ops.

    This is used client-side to compress pending_queue before promoting
    to inflight_op. Reduces wire traffic for fast typists.
    """
    if op_a.op_type == OpType.INSERT and op_b.op_type == OpType.INSERT:
        # op_b inserts immediately after op_a's insertion point
        # e.g. Insert(5,"h") then Insert(6,"i") → Insert(5,"hi")
        if op_b.position == op_a.position + len(op_a.chars):
            return Op(
                op_type=OpType.INSERT,
                position=op_a.position,
                chars=op_a.chars + op_b.chars,
            )
        # op_b inserts at the same position (prepend scenario)
        if op_b.position == op_a.position:
            return Op(
                op_type=OpType.INSERT,
                position=op_a.position,
                chars=op_b.chars + op_a.chars,
            )
        return None

    if op_a.op_type == OpType.DELETE and op_b.op_type == OpType.DELETE:
        # Backspace repeatedly: Delete(10,1) then Delete(9,1) → Delete(9,2)
        if op_b.position == op_a.position - op_b.length:
            return Op(
                op_type=OpType.DELETE,
                position=op_b.position,
                length=op_a.length + op_b.length,
            )
        # Forward delete: Delete(9,1) then Delete(9,1) → Delete(9,2)
        if op_b.position == op_a.position:
            return Op(
                op_type=OpType.DELETE,
                position=op_a.position,
                length=op_a.length + op_b.length,
            )
        return None

    # Mixed types (insert then delete, or delete then insert) cannot be composed
    return None