import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyFragment, applyPerClassStrip, perClassEnabled, fingerprint, stripActionAnchor, actionAnchorStripEnabled, isLayeredFilterFragment, facetFragmentStripEnabled } from "./diezClassify.js";

test("classifyFragment unchanged after move (spot-check)", () => {
    assert.equal(classifyFragment(""), "anchor");
    assert.equal(classifyFragment("section2"), "anchor");
    assert.equal(classifyFragment("mot-de-passe-oublier"), "anchor");
    assert.equal(classifyFragment("/produit/1"), "spa");
    assert.equal(classifyFragment("a&b=c"), "spa");
});

test("applyPerClassStrip: strip anchors (incl empty), keep spa/ambiguous, keep query", () => {
    assert.equal(applyPerClassStrip("https://x.fr/p#"), "https://x.fr/p");
    assert.equal(applyPerClassStrip("https://x.fr/p#section"), "https://x.fr/p");
    assert.equal(applyPerClassStrip("https://x.fr/p#mot-de-passe-oublier"), "https://x.fr/p");
    assert.equal(applyPerClassStrip("https://x.fr/p?a=1#section"), "https://x.fr/p?a=1");
    assert.equal(applyPerClassStrip("https://x.fr/p#/produit/1"), "https://x.fr/p#/produit/1");
    assert.equal(applyPerClassStrip("https://x.fr/p#a&b=c"), "https://x.fr/p#a&b=c");
    assert.equal(applyPerClassStrip("https://x.fr/p"), "https://x.fr/p");
});

test("perClassEnabled reads env at call time", () => {
    delete process.env.DIEZ_PERCLASS_ENABLED;
    assert.equal(perClassEnabled(), false);
    process.env.DIEZ_PERCLASS_ENABLED = "true";
    assert.equal(perClassEnabled(), true);
    delete process.env.DIEZ_PERCLASS_ENABLED;
});

test("fingerprint: identical content equal, whitespace-normalized", () => {
    assert.equal(fingerprint("hello world"), fingerprint("  hello   world\n"));
});
test("fingerprint: differing content differs", () => {
    assert.notEqual(fingerprint("product A specs 500w"), fingerprint("product B specs 800w"));
});
test("fingerprint: empty is stable", () => {
    assert.equal(fingerprint(""), fingerprint("   "));
});

const aaBase = "https://www.capsa-container.com/realisations/page/5/";

test("stripActionAnchor: strips elementor off_canvas toggle (encoded)", () => {
    const url = aaBase + "#elementor-action%3Aaction%3Doff_canvas%3Atoggle%26settings%3DeyJpZCI6IjAwNTljYmEifQ%3D%3D";
    assert.equal(stripActionAnchor(url), aaBase);
});
test("stripActionAnchor: strips popup:open (encoded)", () => {
    const url = aaBase + "#elementor-action%3Aaction%3Dpopup%3Aopen%26settings%3DeyJpZCI6IjYwODcifQ%3D%3D";
    assert.equal(stripActionAnchor(url), aaBase);
});
test("stripActionAnchor: strips an already-decoded action-anchor", () => {
    assert.equal(stripActionAnchor(aaBase + "#elementor-action:action=off_canvas:open&settings=eyJ9"), aaBase);
});
test("stripActionAnchor: keeps a real SPA hash route", () => {
    const url = aaBase + "#/products?page=2";
    assert.equal(stripActionAnchor(url), url);
});
test("stripActionAnchor: keeps a bare named anchor", () => {
    const url = aaBase + "#section-2";
    assert.equal(stripActionAnchor(url), url);
});
test("stripActionAnchor: keeps token:colon fragment with no '=' payload", () => {
    const url = aaBase + "#tab:overview";
    assert.equal(stripActionAnchor(url), url);
});
test("stripActionAnchor: returns a url with no fragment unchanged", () => {
    assert.equal(stripActionAnchor(aaBase), aaBase);
});
test("stripActionAnchor: does not throw on malformed percent-encoding", () => {
    const url = aaBase + "#elementor-action:action=x&bad=%E0%A4%A";
    assert.doesNotThrow(() => stripActionAnchor(url));
});
test("stripActionAnchor: strips ce-action fragments (addToCart, buyNow, braces, quickview)", () => {
    for (const frag of ["ce-action=addToCart", "ce-action=buyNow", "ce-action=addToCart{}", "ce-action=quickview"]) {
        assert.equal(stripActionAnchor(aaBase + "#" + frag), aaBase, frag);
    }
});
test("stripActionAnchor: strips a bare or prefixed action= key, any case", () => {
    for (const frag of ["action=register", "Action=x", "my_action=1"]) {
        assert.equal(stripActionAnchor(aaBase + "#" + frag), aaBase, frag);
    }
});
test("stripActionAnchor: still strips elementor-action forms, raw and encoded", () => {
    for (const frag of ["elementor-action:action=popup:open", "elementor-action%3Aaction%3Dpopup%3Aopen"]) {
        assert.equal(stripActionAnchor(aaBase + "#" + frag), aaBase, frag);
    }
});
test("stripActionAnchor: keeps SPA routes, named anchors and words merely ending in action", () => {
    for (const frag of ["/route/x", "section", "tab:overview", "transaction=1", "faction=1"]) {
        const url = aaBase + "#" + frag;
        assert.equal(stripActionAnchor(url), url, frag);
    }
});
test("action anchors: flag OFF leaves the url intact, ON strips it (call-site gate shape)", () => {
    const url = aaBase + "#ce-action=addToCart";
    const gated = (u: string): string => (actionAnchorStripEnabled() ? stripActionAnchor(u) : u);
    const saved = process.env.STRIP_ACTION_ANCHORS;
    try {
        delete process.env.STRIP_ACTION_ANCHORS;
        assert.equal(gated(url), url);
        process.env.STRIP_ACTION_ANCHORS = "true";
        assert.equal(gated(url), aaBase);
    } finally {
        if (saved === undefined) delete process.env.STRIP_ACTION_ANCHORS;
        else process.env.STRIP_ACTION_ANCHORS = saved;
    }
});
test("actionAnchorStripEnabled: reads env at call time, default false, true only for 'true'", () => {
    delete process.env.STRIP_ACTION_ANCHORS;
    assert.equal(actionAnchorStripEnabled(), false);
    process.env.STRIP_ACTION_ANCHORS = "TRUE";
    assert.equal(actionAnchorStripEnabled(), true);
    process.env.STRIP_ACTION_ANCHORS = "1";
    assert.equal(actionAnchorStripEnabled(), false);
    delete process.env.STRIP_ACTION_ANCHORS;
});

// A517 — PrestaShop 1.6 "blocklayered" filter fragments (DIEZ_FACET_STRIP_ENABLED).
const lfBase = "https://www.equiprestodiffusion.fr/22-equipements-frigorifiques-professionnels";
// Real fragments: brief (dataset of crawl 312-2495-1792738693) + review R2 (two 3-segment filters).
const lfFilterFragments = [
    "categories-caves_a_vin-cellules_de_refroidissement_et_de_congelation-fontaines_refrigerees/fabricant-sayl_barcelona-casselin",
    "categories-caves_a_vin-cellules_de_refroidissement_et_de_congelation-fontaines_refrigerees",
    "categories-caves_a_vin/page-2",
    "egouttoir-egouttoir_a_droite/passage_de_lave_vaisselle-sans_passage_de_lave_vaisselle/profondeur-600_mm",
    "egouttoir-sans_egouttoir/inox_largeur-600/passage_de_lave_vaisselle-sans_passage_de_lave_vaisselle",
];
const lfKeptUrls = [
    "https://www.equiprestodiffusion.fr/27-materiels-de-lavage-professionnels#/page-7",
    lfBase + "#/page-12",
    "https://x.fr/app#/produits/42",
    "https://x.fr/fauteuil.html#/10-couleur-rouge",
    "https://x.fr/fauteuil.html#/1-taille-s/2-couleur-noir",
    "https://x.fr/cloture.html#1009_25-couleur-gris_7016/480753-lot_de-3_exemplaires",
    "https://x.fr/p#!/route/1",
];
// Pre-A517 applyPerClassStrip, verbatim: the flag-OFF reference.
const legacyPerClassStrip = (url: string): string => {
    const i = url.indexOf("#");
    if (i === -1) return url;
    return classifyFragment(url.slice(i + 1)) === "anchor" ? url.slice(0, i) : url;
};
const withFacetFlag = (value: string | undefined, fn: () => void): void => {
    const saved = process.env.DIEZ_FACET_STRIP_ENABLED;
    try {
        if (value === undefined) delete process.env.DIEZ_FACET_STRIP_ENABLED;
        else process.env.DIEZ_FACET_STRIP_ENABLED = value;
        fn();
    } finally {
        if (saved === undefined) delete process.env.DIEZ_FACET_STRIP_ENABLED;
        else process.env.DIEZ_FACET_STRIP_ENABLED = saved;
    }
};

test("A517 flag ON: blocklayered filter fragments are stripped (multi-segment, long single segment, filter + page-N)", () => {
    withFacetFlag("true", () => {
        for (const frag of lfFilterFragments) assert.equal(applyPerClassStrip(lfBase + "#" + frag), lfBase, frag);
    });
});
test("A517 flag ON: pagination, SPA routes and product combinations are kept", () => {
    withFacetFlag("true", () => {
        for (const url of lfKeptUrls) assert.equal(applyPerClassStrip(url), url, url);
    });
});
test("A517 flag OFF: every output is identical to the pre-A517 strip", () => {
    const urls = [
        ...lfFilterFragments.map((f) => lfBase + "#" + f),
        ...lfKeptUrls,
        "https://x.fr/p#", "https://x.fr/p#section", "https://x.fr/p#mot-de-passe-oublier",
        "https://x.fr/p?a=1#section", "https://x.fr/p#/produit/1", "https://x.fr/p#a&b=c", "https://x.fr/p",
    ];
    for (const value of [undefined, "false"]) {
        withFacetFlag(value, () => {
            for (const url of urls) assert.equal(applyPerClassStrip(url), legacyPerClassStrip(url), url);
        });
    }
    // Flag off, the filter URLs keep their fragment (the A517 defect, left as is).
    withFacetFlag(undefined, () => {
        for (const frag of lfFilterFragments) assert.equal(applyPerClassStrip(lfBase + "#" + frag), lfBase + "#" + frag, frag);
    });
});
test("A517 isLayeredFilterFragment: shape rules (encoded, '!', page-only, case, malformed)", () => {
    assert.equal(isLayeredFilterFragment("categories-caves_a_vin%2Ffabricant-casselin"), true);
    assert.equal(isLayeredFilterFragment("!categories-x/fabricant-y"), true);
    assert.equal(isLayeredFilterFragment("prix-10.5-50/fabricant-y"), true);
    assert.equal(isLayeredFilterFragment("page-2"), false);
    assert.equal(isLayeredFilterFragment("page-2/page-3"), false);
    assert.equal(isLayeredFilterFragment("/categories-x/fabricant-y"), false);
    assert.equal(isLayeredFilterFragment("Categories-X/fabricant-y"), false);
    assert.equal(isLayeredFilterFragment("categories-x/"), false);
    assert.equal(isLayeredFilterFragment(""), false);
    assert.doesNotThrow(() => isLayeredFilterFragment("categories-%E0%A4%A"));
});
test("A517 facetFragmentStripEnabled: reads env at call time, default false, true only for 'true'", () => {
    withFacetFlag(undefined, () => assert.equal(facetFragmentStripEnabled(), false));
    withFacetFlag("TRUE", () => assert.equal(facetFragmentStripEnabled(), true));
    withFacetFlag("1", () => assert.equal(facetFragmentStripEnabled(), false));
});
