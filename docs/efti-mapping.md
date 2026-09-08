# The eFTI mapping

*Where each field of the [structured shipment export](shipment-export.md) lands in the
eFTI common data set, and what the data set asks for that this application does not
hold. Measured, not asserted: `backend/app/services/efti.py` reads the seed and the
mapping and counts; `backend/tests/test_efti.py` keeps the numbers on this page equal
to what it counts.*

## What the eFTI data set is

Regulation (EU) 2020/1056 on electronic freight transport information obliges the
authorities of the Member States to accept, from **9 July 2027**, the information that
EU and national transport law asks of an operator in electronic form, through certified
eFTI platforms. Its Article 7 had the Commission establish what those platforms
exchange, and [Commission Delegated Regulation (EU) 2024/2024](http://data.europa.eu/eli/reg_del/2024/2024/oj) of
26 July 2024 does so in its Annex:

- **Table 1, the eFTI common data set** — 681 data objects in one hierarchy: 148 data
  classes (`ASBIE…`), 409 data elements (`BBIE`) and 123 supplementary components
  (`SC`, a unit or a format code that follows its element), each with an identifier
  `eFTIxxx`, a name, a definition, a data type, a format and a code list. It is a profile
  of the UN/CEFACT Multimodal Transport reference data model, which is why its names
  read the way they do.
- **Table 2, the subsets for the EU legal acts** — per provision, which elements it asks
  for and with what status: **M** mandatory, **C** conditional, **O** optional, **D\***
  a supplementary component that follows its element. EU01 is Article 6(1) of
  Regulation No 11 (the road transport document), EU02 Directive 92/106/EEC (combined
  transport), EU03 Regulation (EC) No 1072/2009 (cabotage), **EU05a, EU05b and EU05c**
  the ADR, RID and ADN transport documents under Directive 2008/68/EC, EU06 air cargo
  security.
- Tables 3–29, the subsets for national provisions (one per Member State), not taken
  here; **Table 30**, the 53 code lists and which codes each allows; **Table 31**, the
  122 business rules the subsets refer to (when a conditional element applies).

`scripts/build_efti_seed.py` reads the Official Journal PDF (789 pages, sha256
`991b1a28bff53ae6…`) and writes Tables 1, 2, 30 and 31 as JSON under
`backend/seed/efti/`. The regulation is reusable under the Commission's reuse decision;
the seed carries the ELI and the checksum of the file it was built from.

## What EMCargo is in this

Not an eFTI platform. That is a certification regime for platform providers, and the
platform holds the data, answers the authority and keeps the audit trail. What a
documentation tool can be is **connectable**: every shipment can already leave as
structured data (v1.161.0), and this page says, element by element, which eFTI data
element each of its fields answers. A platform, or a plugin talking to one, takes it
from there — and knows from the same page what it has to ask the user for that this
application never held.

The mapping is a hand-written table, `backend/app/config/efti_mapping.json`, one entry
per eFTI element the export can answer, in three kinds:

- **field** — the export carries the value as such;
- **derived** — the application works it out (a tunnel code from Table A, the 1.1.3.6
  points, a country read off a route field the way the customs route reader does);
- **translated** — the export carries the value in its own vocabulary and a platform
  translates it into the element's code list (a modality into a Recommendation 19 mode
  code, a packing group into a danger level code).

Nothing here produces a message. That needs the platform's schema, the party model
below, and the per-party signature flow the roadmap names as the second half.

## How much of each subset the export answers

Counted over the data elements a subset asks for with status M, C or O; a
supplementary component follows its element and is not counted twice.

| Subset | Provision | Elements asked | Answered | M | C | O |
|---|---|---|---|---|---|---|
| EU01 | Article 6(1) of Regulation No 11 — the road transport document | 50 | 19 | 4 of 24 | 7 of 12 | 8 of 14 |
| EU05a | Directive 2008/68/EC Annex I — ADR, the road dangerous goods transport document | 124 | 41 | 3 of 11 | 33 of 87 | 5 of 26 |
| EU05b | Directive 2008/68/EC Annex II — RID, the rail dangerous goods transport document | 122 | 37 | 4 of 12 | 26 of 82 | 7 of 28 |
| EU05c | Directive 2008/68/EC Annex III — ADN, the inland waterway dangerous goods transport document | 128 | 39 | 4 of 12 | 30 of 89 | 5 of 27 |

**What is missing, and why, in two groups.**

1. **The party model.** The Annex holds an address as postcode, post office box, street,
   city, country, sub-division, building number, department and house number
   (`eFTI54`–`eFTI62` for the consignor, and the same for the consignee, the carrier,
   the acceptance and the receipt location). EMCargo holds every address as one block
   of text, the way it is written on a consignment note. The country can be read off
   it — and is, for the customs conditions — but the rest cannot be separated reliably
   without asking for it separately, and asking is a change to the details step, the
   address book and the export format. That is the one structural gap, and it is what
   makes the mandatory count of EU01 low: 4 of
   24, the eight consignor address elements and the
   fourteen of the two locations being the ones not answered (`eFTI54` Postcode, `eFTI55` Post office box, `eFTI56` Street name, `eFTI57` City name, `eFTI59` Country sub- division name, `eFTI60` Building number, `eFTI61` Department name, `eFTI62` House number, `eFTI141` Postcode, `eFTI144` Street name, `eFTI145` City name, `eFTI147` Country sub- division name, `eFTI148` Building number, `eFTI151` House number, `eFTI157` Postcode, `eFTI160` Street name, `eFTI161` City name, `eFTI163` Country sub- division name, `eFTI164` Building number, `eFTI167` House number).
2. **What the wizard does not ask.** Class 7 (transport index, isotope, activity, special
   form), fuel gas containment systems (SP 392), fumigated units, the competent
   authority's name, attached documents as binary objects, the carrier's identification
   number and the registration country of the means of transport. Each is a field the
   application could add; none is derivable. In EU05a the mandatory elements not answered
   are `eFTI54` Postcode, `eFTI55` Post office box, `eFTI56` Street name, `eFTI57` City name, `eFTI59` Country sub- division name, `eFTI60` Building number, `eFTI61` Department name, `eFTI62` House number.

## The mapping

Status per subset in the order EU01 / EU05a / EU05b / EU05c; `–` where the subset does
not ask for the element.

| Element | Name | Status | Kind | Export source | Note |
|---|---|---|---|---|---|
| `eFTI39` | Carrier acceptance date | M/–/–/– | field | `consignment.loading_date` | Date of taking over (CMR box 4); the export carries a date, eFTI40 format code 102 (CCYYMMDD). |
| `eFTI41` | Gross mass | C/–/–/– | derived | `goods[].weight_total_kg` | Sum over the lines, in kilograms; eFTI42 unit code KGM. |
| `eFTI45` | Gross volume | C/–/–/– | derived | `goods[].length_cm, width_cm, height_cm, quantity` | Sum of length x width x height x quantity where all three are given; MTQ. Lines without dimensions leave the consignment volume unanswered. |
| `eFTI47` | Packages quantity | –/–/–/– | derived | `goods[].quantity, unit` | Sum of the quantities whose unit is a package count; a line in kilograms or litres does not count packages. |
| `eFTI854` | Cash on delivery amount | –/–/–/– | field | `consignment.cod_amount` | CMR box 16 / CIM box 28. The currency (eFTI855) is not a field of its own; the amount is entered as text. |
| `eFTI858` | Consignor provided information | –/–/–/– | field | `consignment.sender_instructions` | CMR box 13, the sender's instructions. |
| `eFTI1309` | Contract terms text | –/–/–/– | field | `consignment.special_agreements` | CMR box 19, special agreements. |
| `eFTI48` | Information | –/–/–/– | field | `consignment.other_useful_info` | CMR box 13/18 free text. |
| `eFTI1307` | Payment arrangement code | –/–/–/– | translated | `consignment.freight_payment` | prepaid / collect / agreement into CL-030 (UN/EDIFACT 4237); the code values are not in the Annex, the list is referenced by name. |
| `eFTI1149` | Declared value for carriage amount | –/–/–/– | field | `consignment.declared_value` | CIM box 26 declared value; on the AWB instruction declared_value_carriage. Currency eFTI1150 not separated. |
| `eFTI51` | Name | O/O/O/O | field | `consignment.consignor_name` | an..35 in the Annex; the export does not truncate. |
| `eFTI52` | Complete telephone number | O/–/–/– | field | `consignment.consignor_contact` | Free text that holds a telephone number, an email address or a person's name; the export does not separate them, so eFTI53 is answered by the same text. |
| `eFTI58` | Country code | M/M/M/M | derived | `consignment.consignor_address` | The country is read off the address the way the customs route reader does (ISO code or country name on the last line); the other address elements (eFTI54-62) are not separated, see the party model gap. |
| `eFTI68` | Name | –/C/C/C | field | `consignment.consignee_name` |  |
| `eFTI69` | Person name | –/C/C/C | field | `consignment.consignee_contact` | Free text, as for the consignor; eFTI71 answered by the same text. |
| `eFTI76` | Country code | –/C/C/C | derived | `consignment.consignee_address` | Country read off the address; eFTI72-81 not separated. |
| `eFTI87` | Name | –/O/O/O | field | `consignment.carrier_name` |  |
| `eFTI102` | Country code | –/O/O/O | derived | `consignment.carrier_address` | The AVC waybill's carrier address; country read off it. Absent on the CMR, whose carrier box holds the name only. |
| `eFTI1310` | Name | –/–/–/– | field | `consignment.freight_forwarder` |  |
| `eFTI136` | ID | C/–/–/– | derived | `consignment.loading_point` | The UN/LOCODE in brackets when the place was picked from the location database (CL-024 is UN/LOCODE); eFTI137 agency code 6 (UNECE). |
| `eFTI138` | Name | C/–/–/– | field | `consignment.loading_point` | Place of loading / taking over as written; place_of_receipt when it differs is the pre-carriage location, not this one. |
| `eFTI146` | Country code | M/–/–/– | derived | `consignment.loading_point` | Country read off the place; the postal elements eFTI141-151 are not separated. |
| `eFTI152` | ID | O/–/–/– | derived | `consignment.discharge_point` | UN/LOCODE in brackets when picked; place_of_delivery and final_destination outrank it as the receipt location when filled. |
| `eFTI154` | Name | C/–/–/– | field | `consignment.place_of_delivery` | Falls back to discharge_point when no separate delivery place is given. |
| `eFTI162` | Country code | M/–/–/– | derived | `consignment.discharge_point` | Country read off the receipt place; eFTI157-167 not separated. |
| `eFTI169` | Type | O/–/–/– | translated | `documents[]` | cmr -> 730 Road consignment note. The CIM has no allowed code in CL-026 (720 is not among the allowed codes); 700 Waybill is the generic. imo_dgd, adn_transport_doc: the dangerous goods declaration is a related document (eFTI326 / eFTI833, CL-026 T-codes), not the transport document. |
| `eFTI171` | Issue date | –/–/–/– | field | `consignment.established_date` | CMR box 21 / CIM box 29 date; eFTI1025 format 102. |
| `eFTI179` | Reference ID | –/–/–/– | field | `consignment.shipment_reference, booking_number, purchase_order, customs_mrn, ens_mrn, aes_itn` | One Trade shipment reference per filled field; the reference type code (eFTI181, CL-049 = UN/EDIFACT 1153) is not in the Annex by value and is still to be assigned per field. |
| `eFTI971` | Goods unit quantity | –/C/C/C | field | `goods[].quantity` | Per consignment item (one per goods line); eFTI972 unit code from the line's unit via UNECE Recommendation 20 (CL-031), where a piece is H87 and a kilogram KGM. |
| `eFTI887` | Width | –/–/–/– | translated | `goods[].width_cm` | Centimetres in the export, CMT in Recommendation 20. |
| `eFTI889` | Length | –/–/–/– | translated | `goods[].length_cm` | Centimetres, CMT. |
| `eFTI891` | Height | –/–/–/– | translated | `goods[].height_cm` | Centimetres, CMT. |
| `eFTI699` | Goods description | O/–/–/– | derived | `goods[].description` | The line descriptions, joined; an..512 in the Annex. |
| `eFTI701` | Statistical classification code | O/–/–/– | field | `consignment.nhm_code` | CIM box 24, six digits from the NHM 2025 list (v1.184.0), agency code 12 (UIC) in eFTI702; on the B/L instruction hs_code with agency 1 (CCC). |
| `eFTI581` | Mode code | –/M/–/M | translated | `modality` | road -> 3, rail -> 2, sea -> 1, inland -> 8 (CL-037, Recommendation 19). Mandatory in EU05a and EU05c. |
| `eFTI618` | ID | O/C/C/C | field | `consignment.vehicle_registration` | CMR box 25 / AVC; on the CIM wagon_number, on the ADN document vessel_name. The registration country (eFTI620) is not a field. |
| `eFTI374` | ID | C/–/O/O | field | `consignment.container_number` | CMR, CIM (container_uti_number), IMO DGD, B/L instruction; eFTI375 agency 20 (BIC) for an ISO 6346 number. |
| `eFTI378` | Category code | C/C/C/C | derived | `consignment.container_number` | CN (container) when a container number is given; the other CL-033 categories (tank-vehicle T1, swap body SW, semi-trailer SM) are not asked in the wizard. |
| `eFTI1014` | Reportable quantity | –/C/C/C | derived | `compliance.adr_points.total_points` | The 1.1.3.6 points total over the transport unit, which the Annex calls the reportable quantity (BR-005). |
| `eFTI387` | UNDG ID | –/C/C/C | field | `dangerous_goods[].products[].un_number` | Loaded dangerous goods per used transport equipment: the same UN numbers, when a container is given. |
| `eFTI399` | Reportable quantity | –/C/C/– | derived | `compliance.adr_points.rows[].points` | The points per product. |
| `eFTI232` | UNDG ID | –/C/M/C | field | `dangerous_goods[].products[].un_number` | Four digits, CL-008 = Table A of chapter 3.2. |
| `eFTI235` | Technical name | –/–/M/C | field | `dangerous_goods[].products[].technical_name` | The technical name in brackets after the proper shipping name (SP 274 / 318); mandatory in EU05b (RID). |
| `eFTI236` | Packaging danger level code | –/C/C/C | translated | `dangerous_goods[].products[].packing_group` | I, II, III into CL-036, which also carries the class 7 categories I-WHITE, II-YELLOW, III-YELLOW the application does not hold. |
| `eFTI238` | Gross mass | –/C/C/C | derived | `dangerous_goods[].products[].gross_mass_per_package, quantity_packages` | Gross mass per package times the number of packages; KGM. BR-101: not for UN 3509. |
| `eFTI240` | Hazard type code | –/–/C/C | derived | `compliance.labels` | RID 5.4.1.1.1 (c) / ADN 5.4.1.1.2 (c): the label model numbers from Table A column (5), as the description line prints them; CL-002 is referenced by name, its codes are not in the Annex. |
| `eFTI242` | Hazard classification ID | –/C/C/C | derived | `dangerous_goods[].products[].hazard_number` | The hazard identification number of Table A column (20), as the placarding sheet prints it (CL-016). |
| `eFTI243` | Volume | –/C/C/C | derived | `dangerous_goods[].products[].adr_total_quantity` | When the 1.1.3.6.3 unit of the substance is litres (liquids, and gases by water capacity); LTR. |
| `eFTI247` | Net mass | –/C/C/C | derived | `dangerous_goods[].products[].adr_total_quantity` | When the 1.1.3.6.3 unit is net kilograms (solids); KGM. |
| `eFTI249` | Explosive cargo net mass | –/C/C/C | field | `dangerous_goods[].products[].net_explosive_mass` | Class 1, kilograms (BR-035). |
| `eFTI251` | Proper shipping name | –/C/C/M C | field | `dangerous_goods[].products[].proper_shipping_name` | Supplemented with the technical name where SP 274 applies, which the description line builder does; the export carries the name as resolved for the document's language. |
| `eFTI255` | Tunnel restriction code | –/C/–/– | derived | `dangerous_goods[].products[].tunnel_code` | Table A column (15), CL-042; BR-064: only where the column carries a code other than '-'. |
| `eFTI258` | Hazard category code | –/C/C/– | derived | `dangerous_goods[].products[].transport_category` | CL-023: 0, 1, 1a, 2, 3, 4 — the transport category of Table A column (15), as the points check reads it; BR-007: when 1.1.3.6 is used. |
| `eFTI261` | Limited quantity code | –/–/O/– | field | `dangerous_goods[].products[].limited_quantity` | RID only (CL-021 code 1), optional. |
| `eFTI279` | Temperature measure | –/C/–/C | field | `dangerous_goods[].products[].control_temperature` | 5.4.1.2.3.1; CEL in eFTI280, type code T1 in eFTI281 (CL-013). |
| `eFTI281` | Type code | –/C/–/C | derived | `dangerous_goods[].products[].control_temperature` | T1, the one code CL-013 allows, whenever a control temperature is given. |
| `eFTI283` | Temperature measure | –/C/–/C | field | `dangerous_goods[].products[].emergency_temperature` | 5.4.1.2.3.1; CEL, type T1. |
| `eFTI285` | Type code | –/C/–/C | derived | `dangerous_goods[].products[].emergency_temperature` | T1 whenever an emergency temperature is given. |
| `eFTI296` | Package quantity | –/C/C/C | field | `dangerous_goods[].products[].quantity_packages` | BR-026: carriage in packagings. |
| `eFTI298` | Packaging type text | –/C/C/C | field | `dangerous_goods[].products[].type_of_package` | The packaging as text; the 6.1.2 packaging code (eFTI297, CL-003) is not held as a code. |
| `eFTI301` | Marking text | –/M/M/M | derived | `compliance.package_marking` | The marks and labels chapter 5.2 puts on each package, as the package label sheet derives them: the UN number mark and the label models (BR-088: lithium batteries label 9, class 7 label 7). |
| `eFTI317` | Statement code | –/O/O/C | translated | `dangerous_goods[].products[].is_waste, empty_uncleaned, salvage_packaging, environmentally_hazardous, molten, classified_2_1_2_8, residue_classes, limited_quantity, excepted_quantity` | CL-011: is_waste -> 8 WASTE IN ACCORDANCE WITH 2.1.3.5.5; empty_uncleaned -> 38 EMPTY, UNCLEANED (packagings 28-31 by kind); salvage_packaging -> 6 SALVAGE PACKAGING / 7 SALVAGE PRESSURE RECEPTACLE; environmentally_hazardous -> 4; molten -> 14 MOLTEN; classified_2_1_2_8 -> 13; residue_classes -> 39 RESIDUE, LAST CONTAINED with subject S2; excepted_quantity -> 36. Each is a condition statement of its own (ASBIE1077). |
| `eFTI319` | Statement text | –/C/C/C | derived | `dangerous_goods[].products[].residue_classes, firework_classification, specific_gas_name` | The statement text 5.4.1.1.19 / 5.4.1.2.1 (g) / 5.4.1.2.2 (e) as the description line builder prints it, with the subject code (eFTI309, CL-015) S2, S1, S3. |
| `eFTI309` | Subject type code | –/C/C/C | derived | `dangerous_goods[].products[].residue_classes, firework_classification, specific_gas_name` | CL-015 subject: S2 residues, S1 fireworks classification, S3 name of the gas. |
| `eFTI1133` | Content text | –/C/C/C | field | `dangerous_goods[].products[].technical_name` | The technical name note where a generic or N.O.S. entry is characterised; eFTI1134 subject 4 (CL-044). |
| `eFTI1134` | Subject code | –/C/C/C | derived | `dangerous_goods[].products[].technical_name` | 4 = further characterises a generic or N.O.S. proper shipping name, the case SP 274 covers. |
| `eFTI746` | Explosive cargo net mass | –/C/C/C | derived | `dangerous_goods[].products[].net_explosive_mass` | Sum over the class 1 products, kilograms (BR-035). |
| `eFTI1751` | Reportable quantity | –/C/–/– | derived | `compliance.adr_points.total_points` | The reportable quantity the 1.1.3.6 exemption is calculated on: the points total, against the threshold of 1,000. |
| `eFTI1752` | Hazard category code | –/C/–/– | derived | `compliance.adr_points.rows[].transport_category` | CL-023, the category each product's points were counted in. |
| `eFTI382` | Full/empty code | –/C/C/C | translated | `dangerous_goods[].products[].empty_uncleaned` | T14 Empty, uncleaned when every product on the equipment is an empty uncleaned means of containment; otherwise not answered. |
| `eFTI703` | Type code | O/–/–/– | derived | `consignment.customs_mrn` | CL-014: 1 when Regulation No 11 applies. The application does not decide that; it can only say a customs declaration exists. |
| `eFTI712` | Information | –/O/O/O | field | `dangerous_goods[].products[].additional_information` | General information on the dangerous goods, free text. |

## What has to happen next

Recorded so the next step starts from here rather than from nothing:

1. **Split the addresses.** Postcode, street and house number, city, country as fields
   of their own on the details step and in the address book, with the one-block address
   kept for the paper. This closes the party model gap for every subset at once.
2. **Assign the code lists by value.** Recommendation 20 units (CL-031), the payment
   arrangement codes (CL-030), the reference type codes (CL-049) and the packaging codes
   of 6.1.2 (CL-003) are referenced by name in the Annex; the values have to come from
   the UNECE code lists themselves (the D.16A directory in the reference folder carries
   4237, 1153 and 6411).
3. **An eFTI view of the export** — the same structure keyed by `eFTIxxx`, produced by
   the export step beside the JSON — once 1 and 2 are done; producing it before then
   would be a file that looks like the standard's while carrying something subtly
   different, which is the failure this page exists to prevent.
4. **The signature flow.** Consignor, carrier and consignee each confirm their part
   (`ASBIE1033`, `ASBIE1045`, `ASBIE1038` — confirmed data set authentication); a
   legal-weight question before a technical one.
