(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CAFormat = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  // Plain words for the engine's flag codes. The workbook keeps the codes (they
  // are filterable), but a CA should never have to read "currency_unknown".
  const FLAG_LABELS = {
    currency_unknown: "Currency not stated",
    currency_ambiguous: "Currency unclear",
    gstin_checksum: "GSTIN check digit wrong",
    gstin_format: "GSTIN format wrong",
    hsn_length: "HSN has the wrong length",
    hsn_missing: "HSN missing",
    hsn_rate: "HSN rate looks off",
    invoice_math: "Total does not equal taxable + tax",
    invoice_number_missing: "Invoice number missing",
    date_missing: "Date missing",
    date_unlabelled: "Date could not be labelled",
    taxable_derived: "Taxable value worked out",
    tax_derived: "Tax worked out",
    invoice_value_derived: "Invoice value worked out",
    item_layout_uncertain: "Line items uncertain",
    unparsed_rows: "Some rows unread",
    utgst: "UTGST, not SGST",
    inferred_from_balance: "Inferred from balance — needs approval",
    duplicate_source_row: "Repeated line in the statement",
    running_balance_break: "Balance does not carry forward",
    balance_mismatch: "Balance does not match the movement",
    ocr_digit_repair: "Read from a scanned digit, check it",
    inferred_from_balance_approved: "Inferred row approved",
  };

  function flagLabel(flag) {
    const key = String(flag || "").trim();
    if (FLAG_LABELS[key]) return FLAG_LABELS[key];
    if (key.startsWith("sap_")) return "SAP export note";
    return key.replace(/_/g, " ");
  }

  function flagList(row) {
    let raw = row && (row.flags != null ? row.flags : row.validation_flags);
    if (raw == null || raw === "") return [];
    if (Array.isArray(raw)) return raw.map(String).map((item) => item.trim()).filter(Boolean);
    if (typeof raw === "string") {
      const trimmed = raw.trim();
      if (trimmed.startsWith("[")) {
        try {
          const parsed = JSON.parse(trimmed);
          if (Array.isArray(parsed)) {
            return parsed.map(String).map((item) => item.trim()).filter(Boolean);
          }
        } catch {
          /* fall through */
        }
      }
      return trimmed.split(/[,;]+/).map((item) => item.trim()).filter(Boolean);
    }
    return [];
  }

  function approvalText(row) {
    const approval = String(row.approval || "").toLowerCase();
    if (approval === "approved") return "Approved — released into the pack";
    if (approval === "rejected") return "Left out of the pack";
    return "Inferred from the balance gap — not in the statement";
  }

  function isInferredRow(row) {
    if (row && row.needs_approval === true) return true;
    const flags = row && row.flags;
    return Array.isArray(flags) && flags.indexOf("inferred_from_balance") !== -1;
  }

  function money(value, currency) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    const code = typeof currency === "string" ? currency.trim().toUpperCase() : "";
    if (/^[A-Z]{3}$/.test(code)) {
      try {
        return new Intl.NumberFormat("en-IN", {
          style: "currency",
          currency: code,
          currencyDisplay: "code",
        }).format(number);
      } catch {
        /* fall through to a neutral decimal format */
      }
    }
    return number.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function dash(value) {
    if (value === null || value === undefined || value === "") return "—";
    return String(value);
  }

  function formatReconMoney(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num)) return "₹0.00";
    return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function formatWhen(value) {
    if (!value) return "";
    const when = new Date(value);
    if (Number.isNaN(when.getTime())) return "";
    return when.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatFileSize(size) {
    const value = Number(size);
    if (!Number.isFinite(value) || value <= 0) return "";
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) {
      return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`;
    }
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }

  // "1 row", "2 rows" - used everywhere a count is shown to the CA.
  function rowsLabel(count) {
    const n = Number(count) || 0;
    return `${n} ${n === 1 ? "row" : "rows"}`;
  }

  function looksLikeGstin(value) {
    if (value === null || value === undefined || value === "") return false;
    return String(value).trim().length === 15;
  }

  function cropCaptionValue(field, value, currency) {
    if (field === "supplier_gstin" || looksLikeGstin(value)) {
      const raw = value === null || value === undefined ? "" : String(value).trim();
      return raw || "—";
    }
    return money(value, currency);
  }

  function observedText(observed) {
    if (!observed) return "";
    const parts = [];
    if (observed.count !== undefined) parts.push(`${observed.count} line(s)`);
    if (observed.total !== undefined) parts.push(`total ${money(observed.total)}`);
    if (observed.largest !== undefined) parts.push(`largest ${money(observed.largest)}`);
    if (observed.turnover !== undefined) parts.push(`turnover ${money(observed.turnover)}`);
    if (observed.sales_lines !== undefined && observed.count === undefined) {
      parts.push(`${observed.sales_lines} sales line(s)`);
    }
    return parts.join(" · ");
  }

  function thresholdText(threshold) {
    if (!threshold) return "";
    const parts = [];
    if (threshold.amount !== undefined) parts.push(`${money(threshold.amount)}`);
    if (threshold.enhanced) parts.push(`enhanced ${money(threshold.enhanced)}`);
    if (threshold.basis) parts.push(threshold.basis);
    if (threshold.rate) parts.push(threshold.rate);
    if (threshold.as_of) parts.push(threshold.as_of);
    return parts.join(" · ");
  }

  function severityClass(severity) {
    if (severity === "review") return "mismatch";
    if (severity === "check") return "unknown";
    return "mute";
  }

  function severityLabel(severity) {
    if (severity === "review") return "Review";
    if (severity === "check") return "Check";
    return "Note";
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  return {
    FLAG_LABELS,
    flagLabel,
    flagList,
    approvalText,
    isInferredRow,
    money,
    dash,
    formatReconMoney,
    formatWhen,
    formatFileSize,
    rowsLabel,
    looksLikeGstin,
    cropCaptionValue,
    observedText,
    thresholdText,
    severityClass,
    severityLabel,
    escapeHtml,
  };
});
