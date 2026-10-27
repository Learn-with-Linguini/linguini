"""Optional pack-supplied contrast forms, separate from confirmed scene facts."""

from .generation import ApprovedTerm, ApprovedVocabulary


def with_pack_vocabulary(pack, vocabulary):
    terms = list(vocabulary.terms)
    existing = {term.fact_id for term in terms}
    grouped = {}
    for key, form in pack.lexical.get("attribute_forms", {}).items():
        kind, value, agreement = key.split(":", 2)
        grouped.setdefault((kind, value), {})[agreement] = form
    for index, ((kind, value), forms) in enumerate(grouped.items()):
        fid = f"contrast:{kind}:{value}"
        if fid in existing:
            continue
        terms.append(
            ApprovedTerm(
                term_id=f"pack-contrast-{index}",
                fact_id=fid,
                source_text=value,
                target_text=next(iter(forms.values())),
                forms=list(dict.fromkeys(forms.values())),
                forms_by_key=forms,
                part_of_speech="adjective",
                provenance="packData",
                linguistic={"attribute-kind": kind},
            )
        )
    for kind, form in pack.lexical.get("relation_forms", {}).items():
        fid = f"contrast:relation:{kind}"
        if fid in existing:
            continue
        terms.append(
            ApprovedTerm(
                term_id=f"pack-contrast-relation-{kind.replace('_', '-')}",
                fact_id=fid,
                source_text=kind,
                target_text=form,
                forms=[form],
                part_of_speech="preposition",
                provenance="packData",
                linguistic={"relation-kind": kind},
            )
        )
    return ApprovedVocabulary(terms=terms)
