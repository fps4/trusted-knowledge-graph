package tkg.access_test

import data.tkg.access

fixture := {
	"policy_version": "test",
	"disclosure": "withheld-count",
	"baseline": {
		"ID-01": {"rule": "ID-01"},
		"ID-02": {"rule": "ID-02"},
		"ID-03": {"rule": "ID-03"},
		"LN-01": {"rule": "LN-01"},
	},
	"principals": {
		"mara": {"kind": "person", "role": null, "person": "P-1", "practice_area": "am", "office": "AMS"},
		"sanne": {"kind": "person", "role": null, "person": "P-2", "practice_area": "fi", "office": "LON"},
		"fi-insider": {"kind": "person", "role": null, "person": "P-3", "practice_area": "fi", "office": "AMS"},
		"kim": {"kind": "person", "role": null, "person": "P-4", "practice_area": "am", "office": "AMS"},
		"percy": {"kind": "service", "role": null, "person": null, "practice_area": null, "office": null},
		"risk": {"kind": "person", "role": "risk", "person": null, "practice_area": null, "office": null},
	},
	"restrictions": {
		"M-B": [{
			"rule": "B-03", "kind": "barrier", "insiders": ["P-1", "P-3"],
			"screened": {"people": ["P-2"], "practice_areas": ["fi"], "offices": []},
			"owner": "Risk", "set_on": "2022-03-14", "set_by": "Risk", "source": "config/barriers.yaml",
		}],
		"M-N": [{
			"rule": "B-11", "kind": "need-to-know", "insiders": ["P-1"],
			"screened": {"people": [], "practice_areas": [], "offices": []},
			"owner": "Risk", "set_on": "2023-11-27", "set_by": "Risk", "source": "config/barriers.yaml",
		}],
	},
}

decide(who, ms, lin) := d if {
	d := access.decision with data.barriers as fixture
		with input as {"principal": who, "matters": ms, "lineage": lin}
}

test_an_unrestricted_matter_is_allowed if {
	decide("sanne", ["M-FREE"], {}).matters["M-FREE"].allow
}

test_the_screened_person_is_denied_with_the_rule if {
	d := decide("sanne", ["M-B"], {}).matters["M-B"]
	not d.allow
	d.grounds[0].rule == "B-03"
	d.grounds[0].owner == "Risk"
}

test_the_grounds_do_not_say_who_else_is_inside_or_screened if {
	g := decide("sanne", ["M-B"], {}).matters["M-B"].grounds[0]
	not g.insiders
	not g.screened
}

test_the_lead_is_inside if {
	decide("mara", ["M-B"], {}).matters["M-B"].allow
}

test_an_insider_wins_over_a_group_screen if {
	decide("fi-insider", ["M-B"], {}).matters["M-B"].allow
}

test_a_barrier_does_not_deny_the_unscreened if {
	decide("kim", ["M-B"], {}).matters["M-B"].allow
}

test_need_to_know_denies_everyone_outside if {
	not decide("kim", ["M-N"], {}).matters["M-N"].allow
	decide("mara", ["M-N"], {}).matters["M-N"].allow
}

test_a_graph_inherits_the_barrier_of_its_lineage if {
	d := decide("sanne", [], {"g:x": ["M-B"]}).graphs["g:x"]
	not d.allow
	d.grounds[0].rule == "B-03"
	d.grounds[0].via == "M-B"
}

test_a_graph_is_allowed_when_its_whole_lineage_is if {
	decide("sanne", [], {"g:x": ["M-FREE"]}).graphs["g:x"].allow
}

test_one_restricted_ancestor_is_enough if {
	not decide("sanne", [], {"g:x": ["M-FREE", "M-B"]}).graphs["g:x"].allow
}

test_a_graph_with_no_lineage_is_shown_to_no_one if {
	d := decide("mara", [], {"g:orphan": []}).graphs["g:orphan"]
	not d.allow
	d.grounds[0].rule == "LN-01"
}

test_a_service_identity_sees_nothing if {
	d := decide("percy", ["M-FREE"], {}).matters["M-FREE"]
	not d.allow
	d.grounds[0].rule == "ID-02"
}

test_an_unknown_principal_sees_nothing if {
	not decide("nobody", ["M-FREE"], {}).matters["M-FREE"].allow
}

test_risk_sees_no_matter_content if {
	d := decide("risk", ["M-FREE"], {}).matters["M-FREE"]
	not d.allow
	d.grounds[0].rule == "ID-03"
}
