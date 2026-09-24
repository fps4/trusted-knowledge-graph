# The access decision. Written by hand and reviewed; it evaluates data compiled
# from config/barriers.yaml (build/opa/data.json) and never encodes a rule of its
# own. See docs/decisions/0007 and 0008.
#
# Input, from the resolver:
#   principal  the person asking, as asserted by their MCP container
#   matters    every matter the question's candidate query reached
#   lineage    derived graph -> the matters it derives from, transitively,
#              computed by SPARQL over prov:wasDerivedFrom+ before this call
#
# Output: allow or deny per matter and per graph, with the grounds — the rule, its
# owner, when and by whom it was set, and the file it lives in. explain() returns
# the grounds verbatim. The compiled data lives at data.barriers — apart from the
# rules, so neither can shadow the other.
package tkg.access

p := data.barriers.principals[input.principal]

# ── who is asking, before any matter is considered ──────────────────────────
default principal_grounds := []

principal_grounds := [data.barriers.baseline["ID-01"]] if not data.barriers.principals[input.principal]

principal_grounds := [data.barriers.baseline["ID-02"]] if p.kind == "service"

principal_grounds := [data.barriers.baseline["ID-03"]] if p.role == "risk"

# ── the rules on one matter ─────────────────────────────────────────────────
restrictions_on(m) := object.get(data.barriers.restrictions, m, [])

inside(r) if p.person in r.insiders

screened(r) if p.person in r.screened.people

screened(r) if p.practice_area in r.screened.practice_areas

screened(r) if p.office in r.screened.offices

# need-to-know: default deny, insiders only.
denies(r) if {
	r.kind == "need-to-know"
	not inside(r)
}

# barrier: default allow, the screened are denied — unless they are inside.
# The matter team was put there by the process that set the barrier.
denies(r) if {
	r.kind == "barrier"
	not inside(r)
	screened(r)
}

# Grounds carry the rule, never who else is inside or screened by it.
rule_grounds(m) := [object.remove(r, ["insiders", "screened"]) |
	some r in restrictions_on(m)
	denies(r)
]

# ── decisions ───────────────────────────────────────────────────────────────
matters := {m: {"allow": count(g) == 0, "grounds": g} |
	some m in input.matters
	g := array.concat(principal_grounds, rule_grounds(m))
}

# A derived graph inherits the restrictions of every matter in its lineage.
graphs := {gr: {"allow": count(g) == 0, "grounds": g} |
	some gr, ms in input.lineage
	g := array.concat(principal_grounds, lineage_grounds(ms))
}

lineage_grounds(ms) := [data.barriers.baseline["LN-01"]] if count(ms) == 0

lineage_grounds(ms) := [object.union(x, {"via": m}) |
	some m in ms
	some x in rule_grounds(m)
] if {
	count(ms) > 0
}

decision := {
	"policy_version": data.barriers.policy_version,
	"disclosure": data.barriers.disclosure,
	"principal": principal_grounds,
	"matters": matters,
	"graphs": graphs,
}
