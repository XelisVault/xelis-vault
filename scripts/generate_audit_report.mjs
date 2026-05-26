const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, ShadingType, WidthType,
  LevelFormat
} = require('docx');
const fs = require('fs');

const GRAY_LIGHT = "F5F5F4";
const GRAY_BORDER = "CCCCCC";
const RED_BG    = "FEF2F2";
const RED_DARK  = "991B1B";
const RED_MED   = "DC2626";
const ORA_BG    = "FFFBEB";
const ORA_DARK  = "92400E";
const ORA_MED   = "D97706";
const GRN_BG    = "F0FDF4";
const GRN_DARK  = "166534";
const GRN_MED   = "16A34A";
const BLU_BG    = "EFF6FF";
const BLU_DARK  = "1E40AF";
const CODE_BG   = "F8F8F8";
const DARK_TEXT = "1C1917";
const MED_TEXT  = "57534E";

const thinBorder = { style: BorderStyle.SINGLE, size: 1, color: GRAY_BORDER };
const noBorder   = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const allBorders = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };
const noBorders  = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 400, after: 160 },
    children: [new TextRun({ text, bold: true, size: 36, color: DARK_TEXT, font: "Arial" })]
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 320, after: 120 },
    children: [new TextRun({ text, bold: true, size: 28, color: DARK_TEXT, font: "Arial" })]
  });
}

function h3(text, color) {
  return new Paragraph({
    spacing: { before: 240, after: 80 },
    children: [new TextRun({ text, bold: true, size: 24, color: color || DARK_TEXT, font: "Arial" })]
  });
}

function para(runs, spacing) {
  return new Paragraph({
    spacing: { before: 60, after: 100, ...(spacing || {}) },
    children: Array.isArray(runs) ? runs : [new TextRun({ text: runs, size: 22, color: MED_TEXT, font: "Arial" })]
  });
}

function bullet(text, bold_part, rest) {
  const children = [];
  if (bold_part) {
    children.push(new TextRun({ text: bold_part, bold: true, size: 22, color: DARK_TEXT, font: "Arial" }));
    if (rest) children.push(new TextRun({ text: rest, size: 22, color: MED_TEXT, font: "Arial" }));
  } else {
    children.push(new TextRun({ text, size: 22, color: MED_TEXT, font: "Arial" }));
  }
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 60 },
    children
  });
}

function codeBlock(lines) {
  const border = { style: BorderStyle.SINGLE, size: 4, color: "D1D5DB" };
  return new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [9000],
    borders: { top: border, bottom: border, left: border, right: border, insideH: noBorder, insideV: noBorder },
    rows: [new TableRow({ children: [
      new TableCell({
        borders: noBorders,
        shading: { fill: CODE_BG, type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 180, right: 180 },
        width: { size: 9000, type: WidthType.DXA },
        children: lines.map(l => new Paragraph({
          spacing: { before: 0, after: 0 },
          children: [new TextRun({ text: l, font: "Courier New", size: 18, color: DARK_TEXT })]
        }))
      })
    ]})]
  });
}

function badBlock(lines) {
  const border = { style: BorderStyle.SINGLE, size: 4, color: RED_MED };
  return new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [9000],
    borders: { top: border, bottom: border, left: border, right: border, insideH: noBorder, insideV: noBorder },
    rows: [new TableRow({ children: [
      new TableCell({
        borders: noBorders,
        shading: { fill: RED_BG, type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 180, right: 180 },
        width: { size: 9000, type: WidthType.DXA },
        children: lines.map(l => new Paragraph({
          spacing: { before: 0, after: 0 },
          children: [new TextRun({ text: l, font: "Courier New", size: 18, color: RED_DARK })]
        }))
      })
    ]})]
  });
}

function goodBlock(lines) {
  const border = { style: BorderStyle.SINGLE, size: 4, color: GRN_MED };
  return new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [9000],
    borders: { top: border, bottom: border, left: border, right: border, insideH: noBorder, insideV: noBorder },
    rows: [new TableRow({ children: [
      new TableCell({
        borders: noBorders,
        shading: { fill: GRN_BG, type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 180, right: 180 },
        width: { size: 9000, type: WidthType.DXA },
        children: lines.map(l => new Paragraph({
          spacing: { before: 0, after: 0 },
          children: [new TextRun({ text: l, font: "Courier New", size: 18, color: GRN_DARK })]
        }))
      })
    ]})]
  });
}

function infoBox(text, color_bg, color_text, borderColor) {
  const b = { style: BorderStyle.SINGLE, size: 1, color: borderColor || BLU_DARK };
  const lb = { style: BorderStyle.SINGLE, size: 12, color: borderColor || BLU_DARK };
  return new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [9000],
    borders: { top: b, bottom: b, left: lb, right: b, insideH: noBorder, insideV: noBorder },
    rows: [new TableRow({ children: [
      new TableCell({
        borders: noBorders,
        shading: { fill: color_bg || BLU_BG, type: ShadingType.CLEAR },
        margins: { top: 100, bottom: 100, left: 200, right: 180 },
        width: { size: 9000, type: WidthType.DXA },
        children: [new Paragraph({ spacing: { before: 0, after: 0 }, children: [
          new TextRun({ text, size: 20, color: color_text || BLU_DARK, font: "Arial" })
        ]})]
      })
    ]})]
  });
}

function badge(label, bg, color) {
  return new TextRun({ text: ` ${label} `, bold: true, size: 18, color, highlight: undefined, shading: { fill: bg } });
}

function bugTitle(severity, contract, title) {
  const configs = {
    CRITIQUE: { bg: RED_BG,  color: RED_DARK,  label: "CRITIQUE" },
    ELEVE:    { bg: ORA_BG,  color: ORA_DARK,  label: "ELEVÉ   " },
    MOYEN:    { bg: GRN_BG,  color: GRN_DARK,  label: "MOYEN   " },
    MINEUR:   { bg: GRAY_LIGHT, color: MED_TEXT, label: "MINEUR  " },
  };
  const c = configs[severity] || configs.MOYEN;
  return new Paragraph({
    spacing: { before: 280, after: 80 },
    children: [
      new TextRun({ text: `[${c.label}]  `, bold: true, size: 22, color: c.color, font: "Courier New" }),
      new TextRun({ text: `${contract}`, bold: true, size: 22, color: c.color, font: "Arial" }),
      new TextRun({ text: `  —  ${title}`, size: 22, color: DARK_TEXT, font: "Arial" }),
    ]
  });
}

function divider() {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: GRAY_BORDER } },
    children: []
  });
}

function space(n) {
  return new Paragraph({ spacing: { before: 0, after: n || 80 }, children: [] });
}

// ─────────────── DOCUMENT ───────────────
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 600, hanging: 300 } } } }]
    }]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: DARK_TEXT },
        paragraph: { spacing: { before: 400, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: DARK_TEXT },
        paragraph: { spacing: { before: 320, after: 120 }, outlineLevel: 1 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    children: [

      // ── COVER ──────────────────────────────────────────────
      new Paragraph({ spacing: { before: 600, after: 120 }, children: [
        new TextRun({ text: "XELIS VAULT", bold: true, size: 52, color: DARK_TEXT, font: "Arial" })
      ]}),
      new Paragraph({ spacing: { before: 0, after: 80 }, children: [
        new TextRun({ text: "Rapport d'analyse des contrats intelligents", size: 28, color: MED_TEXT, font: "Arial" })
      ]}),
      new Paragraph({ spacing: { before: 0, after: 400 }, children: [
        new TextRun({ text: "Version analysée : fichiers uploadés + GitHub main  ·  Mai 2026", size: 20, color: MED_TEXT, font: "Arial" })
      ]}),
      divider(),

      // ── INTRO ──────────────────────────────────────────────
      space(160),
      para([
        new TextRun({ text: "Ce rapport couvre l'analyse complète de ", size: 22, color: MED_TEXT, font: "Arial" }),
        new TextRun({ text: "20 contrats Silex", bold: true, size: 22, color: DARK_TEXT, font: "Arial" }),
        new TextRun({ text: " du protocole XELIS Vault, croisée avec la bibliothèque standard XELIS (lib.rs). Chaque problème identifié est décrit précisément avec le code fautif et le correctif correspondant.", size: 22, color: MED_TEXT, font: "Arial" }),
      ]),
      space(120),

      // Summary table
      new Table({
        width: { size: 9000, type: WidthType.DXA },
        columnWidths: [2250, 2250, 2250, 2250],
        rows: [
          new TableRow({ children: [
            ["7 Critiques", RED_BG, RED_DARK],
            ["8 Élevés", ORA_BG, ORA_DARK],
            ["6 Moyens", GRN_BG, GRN_DARK],
            ["3 Mineurs", GRAY_LIGHT, MED_TEXT],
          ].map(([t, bg, col]) => new TableCell({
            borders: allBorders,
            shading: { fill: bg, type: ShadingType.CLEAR },
            margins: { top: 120, bottom: 120, left: 160, right: 160 },
            width: { size: 2250, type: WidthType.DXA },
            children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
              new TextRun({ text: t, bold: true, size: 24, color: col, font: "Arial" })
            ]})]
          }))
        })]
      }),
      space(300),

      // ════════════════════════════════════════════════════════
      h1("1. Problème du Playground — \"Opaque Value\" et storage vide"),
      // ════════════════════════════════════════════════════════

      para([
        new TextRun({ text: "C'est le premier problème rencontré. Il s'explique simplement : le playground Silex ", size: 22, color: MED_TEXT, font: "Arial" }),
        new TextRun({ text: "recrée un storage vide à chaque clic sur \"Execute\"", bold: true, size: 22, color: DARK_TEXT, font: "Arial" }),
        new TextRun({ text: ". Ce n'est pas un bug dans ton code.", size: 22, color: MED_TEXT, font: "Arial" }),
      ]),
      space(80),

      h3("Ce qui se passe concrètement"),
      para("Quand tu coches \"Run Constructor\" et que tu cliques Execute, le constructeur tourne et stocke l'adresse admin dans le MockStorage. Mais ce storage existe seulement en mémoire pour cette exécution. Au prochain clic Execute (sans re-cocher Run Constructor), le storage est vide."),
      space(60),
      badBlock([
        "// Exécution 1 : constructeur coché",
        "s.store(\"a\", get_caller())  → admin stocké",
        "",
        "// Exécution 2 : tu appelles propose_price sans constructeur",
        "s.load(\"a\").expect(\"anset\")  → PANIQUE : clé absente",
        "// XELIS affiche \"opaque value\" car le slot est vide et",
        "// il tente quand même de le caster comme Address.",
      ]),
      space(60),
      goodBlock([
        "// RÈGLE : toujours cocher \"Run Constructor\" avant chaque test",
        "// dans le playground.",
        "",
        "// Sur devnet/testnet : le storage persiste normalement.",
        "// Le constructeur tourne une fois au déploiement, c'est tout.",
      ]),
      space(80),
      infoBox("Note : l'affichage Opaque(...) dans le viewer du storage est NORMAL. Les types Address et Hash s'affichent toujours ainsi car ce sont des types opaques. Ce n'est pas une erreur.", BLU_BG, BLU_DARK),

      // ════════════════════════════════════════════════════════
      h1("2. Bugs Critiques — Bloquants en production"),
      // ════════════════════════════════════════════════════════

      para("Ces bugs rendent le protocole non fonctionnel ou exploitable. Ils doivent être corrigés avant tout déploiement."),

      // ── BUG CRITIQUE 1 ──
      bugTitle("CRITIQUE", "PriceOracle", "execute_price() peut fixer le prix XEL à zéro"),
      para("Après un appel réussi à execute_price(), le code stocke 0u64 à la place de la valeur pending. Comme 0 n'est pas None, le prochain appel à execute_price() lit Some(0), passe le require is_some(), et écrit 0 comme prix actif. XEL vaut alors 0 dollar, tout le collatéral devient sans valeur, et tous les vaults sont liquidables instantanément. Le même bug existe dans cancel_pending()."),
      space(60),
      badBlock([
        "// execute_price() — ligne fautive",
        "ws.store(PENDING_PRICE_KEY, 0u64);",
        "// → stocke 0, pas None",
        "// → prochain appel : load() retourne Some(0)",
        "// → require(is_some()) passe",
        "// → ws.store(ACTIVE_PRICE_KEY, 0) → XEL = 0$",
        "",
        "// cancel_pending() — même bug",
        "ws.store(PENDING_PRICE_KEY, 0u64);",
      ]),
      space(60),
      goodBlock([
        "// Fix dans execute_price() et cancel_pending()",
        "ws.delete(PENDING_PRICE_KEY);",
        "ws.delete(PENDING_TOPO_KEY);   // nettoyer aussi le topo",
      ]),

      // ── BUG CRITIQUE 2 ──
      bugTitle("CRITIQUE", "VaultEngine", "get_xel_price() appelle le mauvais entry et mauvais type de retour"),
      para("Le code appelle l'entry 3u16 du contrat PriceOracle. Or l'entry 3 correspond à get_pending_price() qui retourne optional<u64>. L'entry correcte pour get_price() est la 2. De plus, le retour est casté en u64[] (tableau) alors que get_price() retourne un seul u64. Ce triple bug provoque un crash à chaque opération qui dépend du prix (borrow, liquidate, health check, redeem)."),
      space(60),
      badBlock([
        "// Mapping des entries de PriceOracle :",
        "// Entry 0 → propose_price(price: u64)",
        "// Entry 1 → execute_price()",
        "// Entry 2 → get_price(asset: Hash)     ← ce qu'on veut",
        "// Entry 3 → get_pending_price()         ← ce que tu appelles",
        "// Entry 4 → cancel_pending()",
        "// Entry 5 → transfer_admin()",
        "",
        "// Code fautif dans VaultEngine :",
        "let prices: u64[] = oc.call(3u16, [Hash::zero()], {});",
        "return prices[0u32];",
        "// → entry 3 = get_pending_price → retourne optional<u64>",
        "// → u64[] ≠ optional<u64> → CRASH runtime",
      ]),
      space(60),
      goodBlock([
        "// Fix :",
        "let price: u64 = oc.call(2u16, [Hash::zero()], {});",
        "return price;",
      ]),

      // ── BUG CRITIQUE 3 ──
      bugTitle("CRITIQUE", "VaultEngine", "borrow() n'envoie jamais de xUSD à l'emprunteur"),
      para("La dette est enregistrée dans le vault et le borrow_plain est mis à jour, mais aucun xUSD n'est créé ni transféré à l'emprunteur. L'emprunteur supporte une dette réelle sans rien recevoir. La clé XUSD_CONTRACT_KEY est bien stockée via set_xusd_contract() mais n'est jamais utilisée dans borrow()."),
      space(60),
      badBlock([
        "entry borrow(vault_id: u64, amount: u64) -> u64 {",
        "    // ... vérifications du vault ...",
        "    vault.borrow_plain = new_borrow;",
        "    ws.store(get_vault_key(vault_id), vault);",
        "    // FIN — aucun mint, aucun transfert xUSD !",
        "    return new_borrow;",
        "}",
      ]),
      space(60),
      goodBlock([
        "// Après avoir sauvegardé le vault, appeler xUSD :",
        "vault.borrow_plain = new_borrow;",
        "ws.store(get_vault_key(vault_id), vault);",
        "",
        "let xc_hash: Hash = rs.load(XUSD_CONTRACT_KEY).expect(\"xcns\");",
        "let xc: Contract = Contract::new(xc_hash).expect(\"xcnf\");",
        "// entry 1 de xUSD = mint_tokens(to: Address, amount: u64)",
        "xc.call(1u16, [caller, net_amount], {});",
      ]),

      // ── BUG CRITIQUE 4 ──
      bugTitle("CRITIQUE", "VaultEngine", "repay() réduit la dette sans consommer de xUSD"),
      para("N'importe qui peut appeler repay(vault_id, 1000000) sans envoyer un seul xUSD et annuler une dette entière. La fonction ne vérifie aucun dépôt et ne brûle aucun token. La variable XUSD_ASSET_KEY existe dans le storage mais n'est jamais consultée lors du remboursement."),
      space(60),
      badBlock([
        "entry repay(vault_id: u64, amount: u64) -> u64 {",
        "    // MANQUE : get_deposit_for_asset(xusd_hash)",
        "    // MANQUE : burn(repay_amount, xusd_hash)",
        "    vault.borrow_plain = vault.borrow_plain - repay_amount;",
        "    // → dette annulée, zéro xUSD dépensé !",
        "}",
      ]),
      space(60),
      goodBlock([
        "// Ajouter en début de repay() :",
        "let xusd_hash: Hash = rs.load(XUSD_ASSET_KEY).expect(\"xans\");",
        "let dep: optional<u64> = get_deposit_for_asset(xusd_hash);",
        "require(dep.is_some() && dep.unwrap() >= repay_amount, \"nodep\");",
        "let ok: bool = burn(repay_amount, xusd_hash);",
        "require(ok, \"burnfail\");",
        "// Puis réduire la dette normalement",
      ]),

      // ── BUG CRITIQUE 5 ──
      bugTitle("CRITIQUE", "VaultEngine", "liquidate() ne transfère rien au liquidateur"),
      para("Le liquidateur ne paie aucun xUSD pour couvrir la dette et ne reçoit aucun collatéral. La fonction marque simplement le vault comme liquidé. Le collatéral reste bloqué dans le contrat pour toujours, irrécupérable."),
      space(60),
      badBlock([
        "entry liquidate(vault_id: u64) -> u64 {",
        "    // MANQUE : vérifier dépôt xUSD du liquidateur",
        "    // MANQUE : burn(vault.borrow_plain, xusd_hash)",
        "    // MANQUE : transfer(caller, collateral, asset)",
        "    vault.liquidated = true;",
        "    ws.store(get_vault_key(vault_id), vault);",
        "    // → collatéral bloqué à vie dans le contrat",
        "    return vault.collateral_plain;  // retourne mais n'envoie rien",
        "}",
      ]),
      space(60),
      goodBlock([
        "// 1. Liquidateur doit payer la dette en xUSD",
        "let xusd_hash: Hash = rs.load(XUSD_ASSET_KEY).expect(\"xans\");",
        "let dep: optional<u64> = get_deposit_for_asset(xusd_hash);",
        "require(dep.is_some() && dep.unwrap() >= vault.borrow_plain, \"nodep\");",
        "let ok_burn: bool = burn(vault.borrow_plain, xusd_hash);",
        "require(ok_burn, \"burnfail\");",
        "",
        "// 2. Transférer le collatéral (moins pénalité) au liquidateur",
        "let penalty: u64 = vault.collateral_plain * LIQUIDATION_PENALTY / 100;",
        "let net_col: u64 = vault.collateral_plain - penalty;",
        "let ok_tx: bool = transfer(caller, net_col, vault.collateral_asset);",
        "require(ok_tx, \"txfail\");",
      ]),

      // ── BUG CRITIQUE 6 ──
      bugTitle("CRITIQUE", "VaultEngine", "withdraw() bypass le health check si remaining == 0"),
      para("La condition utilise && remaining > 0 dans le test du health check. Si un utilisateur retire tout son collatéral (remaining = 0) avec une dette ouverte, la condition court-circuite et le retrait est accepté. L'utilisateur récupère tout son collatéral et conserve sa dette, laissant le protocole avec une créance non couverte."),
      space(60),
      badBlock([
        "if vault.borrow_plain > 0 && remaining > 0 {",
        "    require_healthy(remaining, vault.borrow_plain);",
        "}",
        "// Si remaining == 0 et borrow_plain > 0 : check IGNORÉ !",
        "// L'utilisateur retire tout avec une dette active.",
      ]),
      space(60),
      goodBlock([
        "if vault.borrow_plain > 0 {",
        "    require(remaining > 0, \"nocol\");  // retrait total interdit",
        "    require_healthy(remaining, vault.borrow_plain);",
        "}",
      ]),

      // ── BUG CRITIQUE 7 ──
      bugTitle("CRITIQUE", "GovernanceVault", "hash du contrat VLT utilisé à la place du hash de l'asset"),
      para("Dans XELIS, un contrat et l'asset qu'il crée ont des hashes différents. VLT_CONTRACT_KEY stocke le hash du contrat VLT. Mais get_deposit_for_asset() et transfer() attendent le hash de l'asset créé par Asset::create(). Aucun utilisateur ne pourra jamais staker car get_deposit_for_asset(contract_hash) ne trouvera aucun dépôt. De même, unstake() essaiera de transférer un asset inexistant."),
      space(60),
      badBlock([
        "// Dans stake() :",
        "let vlt_hash: Hash = Storage::new().load(VLT_CONTRACT_KEY).expect(\"vcns\");",
        "let dep: optional<u64> = get_deposit_for_asset(vlt_hash);",
        "// vlt_hash = hash du CONTRAT VLT, pas de l'ASSET VLT",
        "// → dep sera toujours None → require échoue toujours",
        "",
        "// Dans unstake() :",
        "let ok: bool = transfer(caller, pos.amount, vlt_hash);",
        "// → tente de transférer un asset qui n'existe pas",
      ]),
      space(60),
      goodBlock([
        "// Ajouter une clé pour le hash de l'asset VLT :",
        "const VLT_ASSET_KEY: string = \"va\"",
        "",
        "entry set_vlt_asset(asset_hash: Hash) -> u64 {",
        "    only_admin();",
        "    Storage::new().store(VLT_ASSET_KEY, asset_hash);",
        "    return 0;",
        "}",
        "",
        "// Dans stake() et unstake(), remplacer VLT_CONTRACT_KEY :",
        "let vlt_asset: Hash = Storage::new().load(VLT_ASSET_KEY).expect(\"vans\");",
        "let dep: optional<u64> = get_deposit_for_asset(vlt_asset);",
        "// Dans unstake() :",
        "let ok: bool = transfer(caller, pos.amount, vlt_asset);",
      ]),

      // ════════════════════════════════════════════════════════
      h1("3. Bugs Élevés — Fonctionnels importants"),
      // ════════════════════════════════════════════════════════

      para("Ces bugs n'empêchent pas la compilation mais rendent des fonctionnalités clés incorrectes ou exploitables."),

      // ── BUG ÉLEVÉ 1 ──
      bugTitle("ELEVE", "GovernanceVault", "Le lock est en blocs, pas en jours"),
      para("locked_until: topo + lock_days ajoute lock_days directement au topoheight. Avec un block time de ~2 secondes sur XELIS, un lock de 7 jours dure en réalité 7 blocs soit environ 14 secondes. Le require minimum de 7 est donc un minimum de 14 secondes, pas 7 jours."),
      space(60),
      badBlock([
        "locked_until: topo + lock_days,",
        "// lock_days = 7 → expire dans 7 blocs = ~14 secondes",
      ]),
      space(60),
      goodBlock([
        "const BLOCKS_PER_DAY: u64 = 43200  // à 2 secondes par bloc",
        "",
        "locked_until: topo + lock_days * BLOCKS_PER_DAY,",
        "// lock_days = 7 → expire dans 302 400 blocs = ~7 jours",
      ]),

      // ── BUG ÉLEVÉ 2 ──
      bugTitle("ELEVE", "xUSD · VLT", "transfer_tokens() envoie au caller, le paramètre \"to\" est ignoré"),
      para("Dans XELIS, transfer(A, amount, hash) envoie DU contrat VERS A. Le code passe caller comme destination au lieu de to. Quiconque appelle cette fonction reçoit les tokens indépendamment du paramètre to passé. Le bug est présent dans xUSD (transfer_tokens) et dans VLT (transfer_token)."),
      space(60),
      badBlock([
        "entry transfer_tokens(to: Address, amount: u64) -> u64 {",
        "    let caller: Address = get_caller().expect(\"nocaller\");",
        "    let ok: bool = transfer(caller, amount, hash);",
        "    // → envoie au caller, \"to\" est ignoré !",
        "}",
      ]),
      space(60),
      goodBlock([
        "let ok: bool = transfer(to, amount, hash);  // envoyer à \"to\"",
      ]),

      // ── BUG ÉLEVÉ 3 ──
      bugTitle("ELEVE", "FlashLoan", "Le remboursement n'est pas dans la même transaction"),
      para("Un vrai flash loan doit être remboursé atomiquement dans la même transaction. Ici flash_loan() envoie les fonds et repay_flash_loan() est une entrée séparée dans une transaction ultérieure. L'emprunteur peut prendre les fonds et ne jamais appeler repay. Le contrat n'a aucun mécanisme de recouvrement automatique. C'est une limitation architecturale de XELIS actuelle — les appels cross-contrats atomiques dans une seule transaction ne sont pas encore disponibles. En attendant, une solution de contournement est d'exiger un dépôt collatéral dans flash_loan() au moins égal au montant emprunté."),
      space(60),
      infoBox("Limitation XELIS : les flash loans atomiques nécessitent que plusieurs appels de contrats soient exécutés dans une seule transaction. Vérifier l'évolution du protocole XELIS avant de déployer ce contrat en production.", ORA_BG, ORA_DARK, ORA_MED),

      // ── BUG ÉLEVÉ 4 ──
      bugTitle("ELEVE", "SealedBidAuction", "La révélation doit avoir lieu APRÈS la fin de l'enchère"),
      para("Une enchère scellée (Vickrey) a deux phases distinctes : commit pendant l'enchère, reveal après la fin. Le code impose topo <= auction.end_topo dans reveal_bid(), obligeant la révélation pendant l'enchère. Les enchérisseurs tardifs peuvent voir les offres révélées et surenchérir de justesse. Le caractère scellé est entièrement perdu."),
      space(60),
      badBlock([
        "entry reveal_bid(bid_id: u64, actual_value: u64, nonce: u64) -> u64 {",
        "    // ...",
        "    require(topo <= auction.end_topo, \"ended\");",
        "    // → révélation forcée PENDANT l'enchère = pas scellé !",
        "}",
      ]),
      space(60),
      goodBlock([
        "const REVEAL_WINDOW: u64 = 100  // 100 blocs après la fin",
        "",
        "// Dans reveal_bid() :",
        "require(topo > auction.end_topo, \"still_active\");",
        "require(topo <= auction.end_topo + REVEAL_WINDOW, \"reveal_over\");",
      ]),

      // ── BUG ÉLEVÉ 5 ──
      bugTitle("ELEVE", "SealedBidAuction", "xor_hashes n'est pas une fonction standard XELIS"),
      para("La fonction xor_hashes() utilisée pour créer le commitment des enchères scellées n'apparaît pas dans les fonctions exposées par la bibliothèque standard XELIS (lib.rs). Si elle n'est pas disponible dans l'environnement Silex, le contrat ne compilera pas. De plus, XOR n'est pas un schéma d'engagement cryptographique sûr : la préimage est triviale à calculer si on connaît le nonce."),
      space(60),
      infoBox("Vérifier si xor_hashes est disponible dans ta version de Silex. Si non, utiliser la fonction de hachage disponible dans l'environnement XELIS (sha3 ou équivalent).", ORA_BG, ORA_DARK, ORA_MED),

      // ── BUG ÉLEVÉ 6 ──
      bugTitle("ELEVE", "PrivateInsurance", "Un membre peut drainer le pool en appelant claim_payout() à répétition"),
      para("Il n'y a aucun suivi de qui a déjà réclamé un paiement. Un membre peut appeler claim_payout() en boucle et vider total_premiums jusqu'à ce que le solde soit inférieur à coverage_amount. Un seul membre malveillant suffit à vider l'intégralité du pool."),
      space(60),
      badBlock([
        "entry claim_payout(pool_id: u64) -> u64 {",
        "    require(is_member(...), \"notmem\");",
        "    // MANQUE : vérification que ce membre n'a pas déjà réclamé",
        "    pool.total_premiums -= pool.coverage_amount;",
        "    transfer(caller, pool.coverage_amount, ...);",
        "    // → appelable à l'infini par le même membre !",
        "}",
      ]),
      space(60),
      goodBlock([
        "// Tracker les claims par index de membre",
        "const CLAIM_PREFIX: string = \"cl\"",
        "",
        "fn get_claim_key(pool_id: u64, member_idx: u64) -> string {",
        "    return CLAIM_PREFIX + pool_id.to_string(10u32)",
        "           + \"_\" + member_idx.to_string(10u32);",
        "}",
        "",
        "// Dans claim_payout() : trouver l'index du membre,",
        "// vérifier la clé CLAIM, stocker true après le paiement.",
      ]),

      // ── BUG ÉLEVÉ 7 ──
      bugTitle("ELEVE", "InsurancePool", "claim() ne décrémente pas TOTAL_STAKED_KEY"),
      para("Quand un staker retire ses fonds via claim(), le compteur TOTAL_STAKED_KEY n'est pas mis à jour. Il croît sans jamais descendre. get_total_staked() retourne des valeurs incorrectes après chaque retrait."),
      space(60),
      badBlock([
        "entry claim(position_id: u64) -> u64 {",
        "    pos.claimed = true;",
        "    transfer(caller, pos.amount, Hash::zero());",
        "    // MANQUE : ws.store(TOTAL_STAKED_KEY, total - pos.amount)",
        "}",
      ]),
      space(60),
      goodBlock([
        "let ws: Storage = Storage::new();",
        "let total: u64 = ws.load(TOTAL_STAKED_KEY).unwrap_or(0);",
        "if total >= pos.amount {",
        "    ws.store(TOTAL_STAKED_KEY, total - pos.amount);",
        "}",
      ]),

      // ── BUG ÉLEVÉ 8 ──
      bugTitle("ELEVE", "LendingMarket", "Aucun suivi de dette par emprunteur"),
      para("borrow() transfère des assets sans enregistrer qui a emprunté quoi. repay() accepte un remboursement global sans vérifier si le caller est bien débiteur. N'importe qui peut réduire total_borrows avec une repay() sans avoir jamais emprunté. L'emprunteur original ne peut pas être identifié ni poursuivi."),
      space(60),
      goodBlock([
        "// Ajouter un struct de position emprunteur :",
        "const BORROW_PREFIX: string = \"br\"",
        "",
        "struct BorrowerPosition {",
        "    borrower: Address,",
        "    pool_id: u64,",
        "    amount: u64,",
        "    collateral: u64",
        "}",
        "",
        "// Stocker dans borrow(), vérifier l'owner dans repay()",
      ]),

      // ════════════════════════════════════════════════════════
      h1("4. Bugs Moyens — À corriger avant mainnet"),
      // ════════════════════════════════════════════════════════

      // ── BUG MOYEN 1 ──
      bugTitle("MOYEN", "ComplianceModule", "N'importe qui peut utiliser le record KYC d'un autre"),
      para("is_accredited(record_id) ne vérifie pas que le caller est bien le propriétaire du record. Connaître un record_id approuvé suffit pour passer la vérification d'accréditation, sans être la personne concernée."),
      space(60),
      goodBlock([
        "entry is_accredited(record_id: u64) -> bool {",
        "    let caller: Address = get_caller().expect(\"nocaller\");",
        "    let record: ComplianceRecord = rs.load(...).expect(\"rnf\");",
        "    require(record.address_val == caller, \"notowner\");  // ← ajouter",
        "    if !record.accredited { return false; }",
        "    return check_kyc(record_id);",
        "}",
      ]),

      // ── BUG MOYEN 2 ──
      bugTitle("MOYEN", "SyndicatePool", "Fonds des investisseurs perdus si objectif non atteint"),
      para("Si pool.raised < pool.target_amount quand close_pool() est appelé, la pool se ferme sans rembourser les investisseurs. Leurs fonds restent bloqués à vie dans le contrat. Il est impossible de les récupérer car les positions par investisseur ne sont pas trackées."),
      space(60),
      goodBlock([
        "// Ajouter un struct pour tracker chaque investisseur :",
        "const INVESTOR_PREFIX: string = \"iv\"",
        "struct InvestorPosition { investor: Address, pool_id: u64, amount: u64 }",
        "",
        "// Dans close_pool() si objectif non atteint :",
        "// itérer les InvestorPositions et rembourser chacun",
      ]),

      // ── BUG MOYEN 3 ──
      bugTitle("MOYEN", "TreasuryVault", "Les allocations cumulées peuvent dépasser 100%"),
      para("Chaque allocation est limitée à 10000 bps (100%) individuellement, mais il n'y a aucune vérification que la somme de toutes les allocations reste dans cette limite. Deux allocations de 60% chacune donnent 120% — distribute() échouera à mi-chemin quand le contrat sera à court de fonds."),
      space(60),
      goodBlock([
        "const TOTAL_BPS_KEY: string = \"tbps\"",
        "",
        "// Dans set_allocation() :",
        "let current: u64 = rs.load(TOTAL_BPS_KEY).unwrap_or(0);",
        "require(current + share_bps <= 10000, \"exceeds100pct\");",
        "ws.store(TOTAL_BPS_KEY, current + share_bps);",
        "",
        "// Dans remove_allocation() : décrémenter TOTAL_BPS_KEY",
      ]),

      // ── BUG MOYEN 4 ──
      bugTitle("MOYEN", "LendingMarket", "Mutation de variable immutable → erreur de compilation"),
      para("En Silex, les variables let sont immutables par défaut (comme en Rust). La ligne borrow_amount = available tente de réassigner une variable let, ce qui ne compilera probablement pas."),
      space(60),
      badBlock([
        "let borrow_amount: u64 = max_borrow;",
        "if borrow_amount > available { borrow_amount = available; }  // ERREUR",
      ]),
      space(60),
      goodBlock([
        "let borrow_amount: u64 = if max_borrow > available { available } else { max_borrow };",
      ]),

      // ── BUG MOYEN 5 ──
      bugTitle("MOYEN", "Payroll", "fund_stream() reçoit les fonds mais ne les comptabilise pas par stream"),
      para("fund_stream() vérifie le dépôt et les tokens arrivent bien dans le contrat, mais aucun suivi par stream_id n'est fait. Si plusieurs streams coexistent, il est impossible de savoir lequel est financé. execute_payroll() puisera simplement dans le solde global du contrat sans garantie que ce stream spécifique est couvert."),
      space(60),
      goodBlock([
        "const FUNDED_PREFIX: string = \"sf\"",
        "",
        "// Dans fund_stream() après la vérification :",
        "let current_funded: u64 = rs.load(get_funded_key(stream_id)).unwrap_or(0);",
        "ws.store(get_funded_key(stream_id), current_funded + dep.unwrap());",
        "",
        "// Dans execute_payroll() : vérifier que funded >= amount",
      ]),

      // ── BUG MOYEN 6 ──
      bugTitle("MOYEN", "RevenueShare", "deposit_revenue() attend toujours XEL indépendamment de asset_hash"),
      para("deposit_revenue() fait toujours get_deposit_for_asset(Hash::zero()) c'est-à-dire qu'il attend des XEL, peu importe l'asset_hash configuré dans le share. Si le share est créé avec un asset_hash différent de XEL (Hash::zero()), le dépôt échouera toujours. claim_dividends() vérifie get_balance_for_asset(share.asset_hash) qui sera toujours 0 puisque le contrat n'a reçu que des XEL."),
      space(60),
      goodBlock([
        "// Dans deposit_revenue() :",
        "let dep: optional<u64> = get_deposit_for_asset(share.asset_hash);",
        "// Utiliser share.asset_hash au lieu de Hash::zero()",
        "",
        "// Dans claim_dividends(), transférer share.asset_hash :",
        "let ok: bool = transfer(caller, amount, share.asset_hash);",
      ]),

      // ════════════════════════════════════════════════════════
      h1("5. Bugs Mineurs"),
      // ════════════════════════════════════════════════════════

      // ── BUG MINEUR 1 ──
      bugTitle("MINEUR", "LendingMarket", "withdraw_liquidity() retourne 0 au lieu du montant retiré"),
      para("La variable pos.amount est mise à 0 avant d'être retournée. Le retour de la fonction sera toujours 0."),
      space(60),
      badBlock([
        "pos.amount = 0;",
        "ws.store(get_supplier_key(supply_id), pos);",
        "return pos.amount;  // retourne 0 !",
      ]),
      space(60),
      goodBlock([
        "let withdrawn: u64 = pos.amount;",
        "pos.amount = 0;",
        "ws.store(get_supplier_key(supply_id), pos);",
        "return withdrawn;",
      ]),

      // ── BUG MINEUR 2 ──
      bugTitle("MINEUR", "AssetVault", "Asset ID = id+100, risque de collision"),
      para("Asset::create(id + 100, ...) utilise un ID arbitraire basé sur le compteur de vaults. Si d'autres contrats créent des assets avec des IDs dans la même plage, des collisions sont possibles. Utiliser 0 pour laisser XELIS générer un ID automatiquement et unique."),
      space(60),
      goodBlock([
        "// Utiliser 0 pour un ID auto-généré par XELIS :",
        "let share_asset: Asset = Asset::create(0u64, \"RWA \"..., ...)",
      ]),

      // ── BUG MINEUR 3 ──
      bugTitle("MINEUR", "TreasuryVault", "remove_allocation() ne décrémente pas ALLOC_COUNT_KEY"),
      para("Après suppression d'une allocation, ALLOC_COUNT_KEY n'est pas décrémenté. process_distribute() gère les slots vides via alloc_opt.is_none(), donc ça ne crashe pas. Mais le compteur est incorrect et les nouveaux ajouts ne remplissent pas les trous supprimés."),

      // ════════════════════════════════════════════════════════
      divider(),
      space(160),
      h1("6. Ordre de correction recommandé"),
      // ════════════════════════════════════════════════════════

      para("Corriger dans cet ordre pour débloquer le protocole le plus vite possible :"),
      space(80),
      bullet(null, "Étape 1 — PriceOracle :", " remplacer ws.store(PENDING_PRICE_KEY, 0u64) par ws.delete() dans execute_price() et cancel_pending(). Corriger ensuite l'entry ID (3u16 → 2u16) et le type de retour dans VaultEngine."),
      bullet(null, "Étape 2 — VaultEngine borrow/repay :", " ajouter le mint xUSD dans borrow(), ajouter le dépôt + burn dans repay(), ajouter le transfert collatéral dans liquidate()."),
      bullet(null, "Étape 3 — VaultEngine withdraw :", " corriger la condition du health check."),
      bullet(null, "Étape 4 — GovernanceVault :", " ajouter VLT_ASSET_KEY et set_vlt_asset(), corriger le lock en blocs par jours."),
      bullet(null, "Étape 5 — xUSD et VLT :", " corriger transfer(caller, ...) → transfer(to, ...)."),
      bullet(null, "Étape 6 — Autres contrats :", " appliquer les corrections moyennes et mineures listées ci-dessus."),

      space(200),
      divider(),
      new Paragraph({ spacing: { before: 160, after: 0 }, children: [
        new TextRun({ text: "XelisVault — Rapport généré automatiquement — Mai 2026", size: 18, color: MED_TEXT, font: "Arial" })
      ]}),
    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('XelisVault_Bug_Report.docx', buf);
  console.log('done');
});
