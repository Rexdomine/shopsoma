# ShopSoma — DHL Express (MyDHL API) Integration Summary

**Prepared by:** ShopSoma Engineering  
**Integration Standard:** DHL Express — MyDHL REST API (JSON)  
**Origin Market:** Lagos, Nigeria (`NG`)  
**Supported Lanes:** Nigeria Domestic (`NG` → `NG`) & International Export (`NG` → Global Allow-List)

---

## 1. Executive & Operational Overview

ShopSoma operates a **centralized hub-and-spoke fulfillment model** for fashion apparel and accessories:

1. **Vendor-to-Hub Intake:** Independent designers/vendors send ordered items to the **ShopSoma Fulfillment Hub in Lagos, Nigeria**.
2. **Hub Quality Control & Parcel Verification:** ShopSoma hub staff inspect items, consolidate and seal the parcel, and record the **physical scale weight (`kg`)** and **box dimensions (`L × W × H cm`)**.
3. **DHL Express Outbound Handoff:** Every DHL Express shipment originates strictly from ShopSoma's Lagos Hub (`countryCode: "NG"`). Vendors never book DHL shipments directly.

To keep the integration lean, reliable, and compliant with MyDHL best practices, ShopSoma uses **four core MyDHL API endpoints**:

| Step | MyDHL Endpoint | Purpose in ShopSoma | Trigger |
| :--- | :--- | :--- | :--- |
| **1. Rating** | `POST /rates` | Real-time shipping fee & transit estimate | Customer at Checkout & Admin Hub Quote |
| **2. Booking** | `POST /shipments` | Create AWB, Transport Label, Waybill Doc & Commercial Invoice | ShopSoma Admin after Hub QC & parcel sealing |
| **3. Pickup** | `POST /pickups` | Schedule DHL courier collection at ShopSoma Lagos Hub | ShopSoma Admin ("Notify DHL for Hub Pickup") |
| **4. Tracking** | `GET /shipments/{trackingNumber}/tracking` | Sync shipment checkpoints to order status | Admin refresh / status polling |

---

## 2. Environments, Authentication & Security Controls

### 2.1 Base URLs
The integration enforces fixed official MyDHL base URLs controlled by environment configuration (`DHL_ENVIRONMENT`):
- **Sandbox (Test):** `https://express.api.dhl.com/mydhlapi/test`
- **Production (Live):** `https://express.api.dhl.com/mydhlapi` *(gated behind `DHL_ENVIRONMENT=production` and `DHL_LIVE_ENABLED=true`)*

### 2.2 Authentication & HTTP Headers
All requests are sent over HTTPS (`TLS`) via a dedicated asynchronous client with a `30s` timeout:
- **Authentication:** HTTP Basic Auth (`Authorization: Basic base64(username:password)`) using MyDHL API credentials.
- **Request Headers:**
  - `Accept: application/json`
  - `Content-Type: application/json`
- **Diagnostic Correlation:** Captures the `Message-Reference` response header on errors for DHL support troubleshooting.
- **Log Redaction & PII Safety:** Credentials, HTTP `Authorization` headers, raw request payloads, base64 PDF documents, and customer PII are never written to application logs.

### 2.3 DHL Account Usage
- **Account Role:** `typeCode: "shipper"` using ShopSoma's configured DHL Express account number (`DHL_EXPORT_ACCOUNT_NUMBER`).
- **Sandbox Validation Account:** Verified end-to-end in MyDHL Test using account `365143885`.

---

## 3. Shipping Lanes, Products & Customs Rules

| Attribute | Domestic Nigeria Lane | International Export Lane |
| :--- | :--- | :--- |
| **Origin** | Lagos, Nigeria (`NG`) | Lagos, Nigeria (`NG`) |
| **Destination** | All 36 Nigerian States + FCT (`NG`) | Configurable ISO-2 Allow-List (`GH, US, GB, CA, ZA, KE, AE, FR, DE`) |
| **DHL Product Code** | `N` (`EXPRESS DOMESTIC`) | `P` (`EXPRESS WORLDWIDE`) |
| **Customs Declarable** | `false` | `true` |
| **Incoterm** | N/A | `DAP` *(Delivered at Place — receiver pays import duties/taxes)* |
| **Place of Incoterm** | N/A | `LAGOS` |
| **Export Reason / Type** | N/A | `Permanent` / `commercial` |
| **Units of Measurement** | `metric` (`kg` and `cm`) | `metric` (`kg` and `cm`) |
| **Generated Documents** | Transport Label + Waybill Doc (PDF) | Transport Label + Waybill Doc + DHL Commercial Invoice (PDF) |

---

## 4. Detailed API Call Breakdown

### 4.1 Rate Quoting — `POST /rates`

**When it runs:**
1. **Customer Checkout:** Computes total parcel weight and bounding dimensions from cart items and queries MyDHL for live shipping rates from the Lagos Hub to the customer's shipping address.
2. **Hub Pre-Booking Verification:** Re-verifies rate and service availability against the physically weighed and sealed Hub package prior to booking.

**Key Payload Rules:**
- `plannedShippingDateAndTime`: Formatted as `YYYY-MM-DDT12:00:00GMT+01:00` (next valid business shipping date in `Africa/Lagos`).
- `unitOfMeasurement`: `"metric"`.
- `isCustomsDeclarable`: `false` when `receiverDetails.countryCode == "NG"`, `true` for international destinations.
- `accounts`: `[{"typeCode": "shipper", "number": "<DHL_ACCOUNT_NUMBER>"}]`.
- **Nigerian Address Normalization Fallback:** If a domestic customer enters a suburb/LGA name that triggers a MyDHL `400`/`422` postcode/city validation error, our adapter automatically retries once using the canonical Nigerian state capital and 6-digit NIPOST postal code while preserving the full street/locality lines for delivery.
- **Price Selection:** Parses `products[]` and selects the billing total using price-type priority `BILLC` → `PULCL` → `BASEC` in `NGN` or `USD`.

**Sample Request (`POST /rates` — International Export):**
```json
{
  "plannedShippingDateAndTime": "2026-11-11T12:00:00GMT+01:00",
  "unitOfMeasurement": "metric",
  "isCustomsDeclarable": true,
  "accounts": [
    {
      "typeCode": "shipper",
      "number": "365143885"
    }
  ],
  "customerDetails": {
    "shipperDetails": {
      "postalCode": "100001",
      "cityName": "Lagos",
      "countryCode": "NG",
      "provinceCode": "Lagos",
      "addressLine1": "ShopSoma Hub, Victoria Island"
    },
    "receiverDetails": {
      "postalCode": "10001",
      "cityName": "New York",
      "countryCode": "US",
      "provinceCode": "NY",
      "addressLine1": "350 5th Avenue"
    }
  },
  "packages": [
    {
      "weight": 1.5,
      "dimensions": {
        "length": 35.0,
        "width": 25.0,
        "height": 10.0
      }
    }
  ]
}
```

---

### 4.2 Shipment Creation & Document Generation — `POST /shipments`

**When it runs:**
Triggered by an Admin in the ShopSoma Order Operations Console **only after** the parcel is physically inspected, weighed, measured, and sealed at the Lagos Hub.

**Key Payload Rules:**
- `pickup`: `{"isRequested": false}` — Shipment creation is intentionally decoupled from courier dispatch so hub staff can print/attach labels across multiple parcels before requesting collection.
- `productCode`: `"N"` for domestic Nigeria (`NG`); `"P"` for international exports.
- `customerDetails`:
  - `shipperDetails`: `typeCode: "business"`, Lagos Hub address, phone, company name, and logistics email.
  - `receiverDetails`: `typeCode: "private"`, customer delivery address (split cleanly into max 45-character `addressLine1..3`), phone, full name, and email.
- `outputImageProperties`: Requests a single combined `300 DPI` PDF (`allDocumentsInOneImage: true`, `splitDocumentsByPages: true`):
  - **Transport Label:** `typeCode: "label"`, `templateName: "ECOM26_84_A4_001"`
  - **Archive / Waybill Document:** `typeCode: "waybillDoc"`, `templateName: "ARCH_8X4_A4_002"`, `numberOfCopies: 1`
  - **Commercial Invoice (Exports only):** `typeCode: "invoice"`, `templateName: "COMMERCIAL_INVOICE_P_10"`, `invoiceType: "commercial"`, `languageCode: "eng"`
- `content` & `exportDeclaration` (for International Exports):
  - `isCustomsDeclarable: true`
  - `incoterm: "DAP"`
  - `declaredValue` & `declaredValueCurrency` (matches order currency, e.g. `USD` or `NGN`)
  - `exportDeclaration.placeOfIncoterm: "LAGOS"`
  - `exportDeclaration.shipmentType: "commercial"`
  - `exportDeclaration.exportReasonType: "permanent"`
  - `exportDeclaration.invoice`: `number` (`INV-<ORDER_NUMBER>`), `date`, `function: "both"`, `totalNetWeight`, `totalGrossWeight`
  - `exportDeclaration.lineItems[]`: Itemized description, unit price, quantity (`PCS`), 8-digit HS commodity codes (`outbound` and `inbound`, mapped by apparel/accessory category with `62044200` fallback), `manufacturerCountry: "NG"`, `isTaxesPaid: false`.
- **Idempotency & Non-Retry Guarantee:** Each parcel version is locked in PostgreSQL with an idempotency key before calling `POST /shipments`. Network timeouts are **never** automatically retried to prevent duplicate AWBs; instead, the attempt is flagged for admin reconciliation.

**Sample Request (`POST /shipments` — International Export):**
```json
{
  "plannedShippingDateAndTime": "2026-11-11T12:00:00GMT+01:00",
  "pickup": {
    "isRequested": false
  },
  "productCode": "P",
  "accounts": [
    {
      "typeCode": "shipper",
      "number": "365143885"
    }
  ],
  "customerDetails": {
    "shipperDetails": {
      "postalAddress": {
        "postalCode": "100001",
        "cityName": "Lagos",
        "countryCode": "NG",
        "provinceCode": "Lagos",
        "addressLine1": "ShopSoma Hub, Victoria Island"
      },
      "contactInformation": {
        "companyName": "ShopSoma Hub",
        "fullName": "ShopSoma Dispatch",
        "phone": "+2348012345678",
        "email": "logistics@shopsoma.com"
      },
      "typeCode": "business"
    },
    "receiverDetails": {
      "postalAddress": {
        "postalCode": "10001",
        "cityName": "New York",
        "countryCode": "US",
        "provinceCode": "NY",
        "addressLine1": "350 5th Avenue"
      },
      "contactInformation": {
        "companyName": "Jane Doe",
        "fullName": "Jane Doe",
        "phone": "+12125550199",
        "email": "customer@example.com"
      },
      "typeCode": "private"
    }
  },
  "outputImageProperties": {
    "printerDPI": 300,
    "encodingFormat": "pdf",
    "imageOptions": [
      {
        "typeCode": "label",
        "templateName": "ECOM26_84_A4_001"
      },
      {
        "typeCode": "waybillDoc",
        "templateName": "ARCH_8X4_A4_002",
        "isRequested": true,
        "hideAccountNumber": false,
        "numberOfCopies": 1
      },
      {
        "typeCode": "invoice",
        "templateName": "COMMERCIAL_INVOICE_P_10",
        "isRequested": true,
        "invoiceType": "commercial",
        "languageCode": "eng"
      }
    ],
    "splitTransportAndWaybillDocLabels": true,
    "allDocumentsInOneImage": true,
    "splitDocumentsByPages": true,
    "splitInvoiceAndReceipt": true
  },
  "content": {
    "unitOfMeasurement": "metric",
    "isCustomsDeclarable": true,
    "declaredValue": 180.0,
    "declaredValueCurrency": "USD",
    "incoterm": "DAP",
    "description": "Fashion apparel and accessories",
    "packages": [
      {
        "weight": 1.5,
        "dimensions": {
          "length": 35.0,
          "width": 25.0,
          "height": 10.0
        }
      }
    ],
    "exportDeclaration": {
      "lineItems": [
        {
          "number": 1,
          "description": "Silk Adire Midi Dress",
          "price": 180.0,
          "quantity": {
            "value": 1,
            "unitOfMeasurement": "PCS"
          },
          "commodityCodes": [
            { "typeCode": "outbound", "value": "62044200" },
            { "typeCode": "inbound", "value": "62044200" }
          ],
          "exportReasonType": "permanent",
          "manufacturerCountry": "NG",
          "weight": {
            "netValue": 1.5,
            "grossValue": 1.5
          },
          "isTaxesPaid": false
        }
      ],
      "invoice": {
        "number": "INV-ORD-2026-0001",
        "date": "2026-11-11",
        "function": "both",
        "totalNetWeight": 1.5,
        "totalGrossWeight": 1.5
      },
      "exportReason": "Permanent",
      "exportReasonType": "permanent",
      "placeOfIncoterm": "LAGOS",
      "shipmentType": "commercial"
    }
  }
}
```

**Response Data Persisted:**
- `shipmentTrackingNumber` (10-digit DHL Waybill / AWB)
- Decoded PDF bytes (`documents[0].content`) with SHA-256 integrity hash for Hub label/invoice printing.

---

### 4.3 Courier Pickup Dispatch — `POST /pickups`

**When it runs:**
Once labels and commercial invoices are printed and attached to the sealed parcel at the Lagos Hub, a ShopSoma Admin clicks **"Notify DHL for Hub Pickup"** in the Admin Order Operations view.

**Key Payload Rules:**
- `plannedPickupDateAndTime`: Local Lagos timestamp (`YYYY-MM-DDTHH:MM:SSGMT+01:00`).
- `closeTime`: `"18:00"` (Hub closing time, configurable per request).
- `location`: `"reception"`, `locationType`: `"business"`.
- `shipmentDetails[0]`: Links the pickup directly to the booked `shipmentTrackingNumber`, `productCode` (`N` or `P`), `isCustomsDeclarable`, `declaredValue` + `declaredValueCurrency` (included automatically when `isCustomsDeclarable: true`), and physical `packages` dimensions/weight.
- **Idempotency:** Once `dispatchConfirmationNumbers[0]` is stored on the booking, repeated clicks return the existing confirmation number instead of creating duplicate courier dispatches.

**Sample Request (`POST /pickups` — Export Parcel):**
```json
{
  "plannedPickupDateAndTime": "2026-11-11T14:00:00GMT+01:00",
  "closeTime": "18:00",
  "location": "reception",
  "locationType": "business",
  "accounts": [
    {
      "typeCode": "shipper",
      "number": "365143885"
    }
  ],
  "specialInstructions": [
    {
      "value": "Collect sealed ShopSoma parcel at hub reception",
      "typeCode": "TBD"
    }
  ],
  "remark": "Collect sealed ShopSoma parcel at hub reception",
  "customerDetails": {
    "shipperDetails": {
      "postalAddress": {
        "postalCode": "100001",
        "cityName": "Lagos",
        "countryCode": "NG",
        "provinceCode": "Lagos",
        "addressLine1": "ShopSoma Hub, Victoria Island"
      },
      "contactInformation": {
        "email": "logistics@shopsoma.com",
        "phone": "+2348012345678",
        "companyName": "ShopSoma Hub",
        "fullName": "ShopSoma Dispatch"
      }
    },
    "receiverDetails": {
      "postalAddress": {
        "postalCode": "10001",
        "cityName": "New York",
        "countryCode": "US",
        "provinceCode": "NY",
        "addressLine1": "350 5th Avenue"
      },
      "contactInformation": {
        "email": "customer@example.com",
        "phone": "+12125550199",
        "companyName": "Jane Doe",
        "fullName": "Jane Doe"
      }
    }
  },
  "shipmentDetails": [
    {
      "productCode": "P",
      "localProductCode": "P",
      "accounts": [
        {
          "typeCode": "shipper",
          "number": "365143885"
        }
      ],
      "isCustomsDeclarable": true,
      "declaredValue": 180.0,
      "declaredValueCurrency": "USD",
      "unitOfMeasurement": "metric",
      "shipmentTrackingNumber": "6680221575",
      "packages": [
        {
          "weight": 1.5,
          "dimensions": {
            "length": 35.0,
            "width": 25.0,
            "height": 10.0
          }
        }
      ]
    }
  ]
}
```

---

### 4.4 Shipment Tracking — `GET /shipments/{shipmentTrackingNumber}/tracking`

**When it runs:**
Used to refresh tracking checkpoints for active DHL bookings.

**Behavior:**
- Calls `GET /shipments/{shipmentTrackingNumber}/tracking` with URL-encoded waybill number.
- Maps MyDHL event codes (`PU` Picked Up, `PL`/`DF`/`AR` In Transit, `WC` With Delivery Courier, `OK` Delivered, and exception codes) monotonically into ShopSoma's fulfillment states (`collected` → `in_transit` → `out_for_delivery` → `delivered` / `exception`).
- Persists immutable tracking snapshots for auditability and updates customer-visible tracking status.

---

## 5. Sandbox Verification Evidence (MyDHL Test Environment)

All three transactional flows (`POST /rates`, `POST /shipments`, and `POST /pickups`) have been tested end-to-end against `https://express.api.dhl.com/mydhlapi/test` under test account `365143885`.

The following sandbox reference numbers can be inspected by the DHL Integration / Certification team:

| Test Scenario | Origin → Destination | Product | `POST /rates` | `POST /shipments` (Sandbox AWB) | Documents Generated | `POST /pickups` (Dispatch Confirmation) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Domestic Nigeria** | `Lagos, NG` → `Abuja, NG` | `N` (`EXPRESS DOMESTIC`) | `HTTP 200` (`NGN 13,780.84`) | `HTTP 201` — **`6680221553`** | 2-page PDF (Label + Waybill) | `HTTP 201` — **`CBJ261110000493`** |
| **Export — United States** | `Lagos, NG` → `New York, US` | `P` (`EXPRESS WORLDWIDE`, `DAP`) | `HTTP 200` (`NGN 93,413.70`) | `HTTP 201` — **`6680221575`** | 3-page PDF (Label + Waybill + Commercial Invoice) | `HTTP 201` — **`CBJ261110000360`** |
| **Export — United Kingdom** | `Lagos, NG` → `London, GB` | `P` (`EXPRESS WORLDWIDE`, `DAP`) | `HTTP 200` (`NGN 76,984.62`) | `HTTP 201` — **`6680221505`** | Combined PDF (Label + Waybill + Commercial Invoice) | `HTTP 201` — **`CBJ261110000475`** |

---

## 6. Production Go-Live Checklist

When DHL approves production credentials, cutover requires **zero code changes** — only environment configuration updates:

1. Set `DHL_ENVIRONMENT=production` (switches base URL to `https://express.api.dhl.com/mydhlapi`).
2. Set `DHL_LIVE_ENABLED=true`.
3. Provide production `DHL_API_USERNAME`, `DHL_API_PASSWORD`, and live `DHL_EXPORT_ACCOUNT_NUMBER`.
4. Confirm `DHL_EXPORT_ENABLED=true` and desired `DHL_ALLOWED_EXPORT_COUNTRIES` (`GH,US,GB,CA,ZA,KE,AE,FR,DE`).
5. Enable operational flags (`DHL_ENABLED=true`, `DHL_DOMESTIC_WORKFLOW_ENABLED=true`, `DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=true`, `DHL_DOMESTIC_CHECKOUT_ENABLED=true`).
