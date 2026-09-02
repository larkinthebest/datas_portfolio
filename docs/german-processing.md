# German processing

Unicode NFC, whitespace, soft hyphens and line-break hyphenation are normalized while `ä ö ü ß € § %`
remain intact. Money parsing accepts German thousands/decimal separators and trailing-minus debits.
Date parsing distinguishes day and month precision; downstream extraction must keep semantic fields
such as Buchungsdatum, Valuta, Fälligkeit and Leistungszeitraum separate.

