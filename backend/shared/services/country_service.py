import logging

from shared.models.country import Country

logger = logging.getLogger("ledova_backend")


class CountryService:
    # ISO 3166-1 country code to name mapping (alpha-2 and alpha-3)
    COUNTRY_CODE_MAP = {
        "US": "United States",
        "USA": "United States",
        "GB": "United Kingdom",
        "GBR": "United Kingdom",
        "UK": "United Kingdom",
        "CA": "Canada",
        "CAN": "Canada",
        "AU": "Australia",
        "AUS": "Australia",
        "DE": "Germany",
        "DEU": "Germany",
        "FR": "France",
        "FRA": "France",
        "IT": "Italy",
        "ITA": "Italy",
        "ES": "Spain",
        "ESP": "Spain",
        "JP": "Japan",
        "JPN": "Japan",
        "JE": "Jersey",
        "JEY": "Jersey",
        "CN": "China",
        "CHN": "China",
        "IN": "India",
        "IND": "India",
        "BR": "Brazil",
        "BRA": "Brazil",
        "RU": "Russia",
        "RUS": "Russia",
        "MX": "Mexico",
        "MEX": "Mexico",
        "KR": "South Korea",
        "KOR": "South Korea",
        "KZ": "Kazakhstan",
        "KAZ": "Kazakhstan",
        "KY": "Cayman Islands",
        "CYM": "Cayman Islands",
        "SG": "Singapore",
        "SGP": "Singapore",
        "HK": "Hong Kong",
        "HKG": "Hong Kong",
        "CH": "Switzerland",
        "CHE": "Switzerland",
        "NL": "Netherlands",
        "NLD": "Netherlands",
        "BE": "Belgium",
        "BEL": "Belgium",
        "BM": "Bermuda",
        "BMU": "Bermuda",
        "AT": "Austria",
        "AUT": "Austria",
        "SE": "Sweden",
        "SWE": "Sweden",
        "NO": "Norway",
        "NOR": "Norway",
        "DK": "Denmark",
        "DNK": "Denmark",
        "FI": "Finland",
        "FIN": "Finland",
        "IE": "Ireland",
        "IRL": "Ireland",
        "PL": "Poland",
        "POL": "Poland",
        "PT": "Portugal",
        "PRT": "Portugal",
        "GR": "Greece",
        "GRC": "Greece",
        "CZ": "Czech Republic",
        "CZE": "Czech Republic",
        "HU": "Hungary",
        "HUN": "Hungary",
        "RO": "Romania",
        "ROU": "Romania",
        "BG": "Bulgaria",
        "BGR": "Bulgaria",
        "HR": "Croatia",
        "HRV": "Croatia",
        "SI": "Slovenia",
        "SVN": "Slovenia",
        "SK": "Slovakia",
        "SVK": "Slovakia",
        "EE": "Estonia",
        "EST": "Estonia",
        "LV": "Latvia",
        "LVA": "Latvia",
        "LT": "Lithuania",
        "LTU": "Lithuania",
        "LU": "Luxembourg",
        "LUX": "Luxembourg",
        "MT": "Malta",
        "MLT": "Malta",
        "CY": "Cyprus",
        "CYP": "Cyprus",
        "TR": "Turkey",
        "TUR": "Turkey",
        "TW": "Taiwan",
        "TWN": "Taiwan",
        "IL": "Israel",
        "ISR": "Israel",
        "SA": "Saudi Arabia",
        "SAU": "Saudi Arabia",
        "AE": "United Arab Emirates",
        "ARE": "United Arab Emirates",
        "EG": "Egypt",
        "EGY": "Egypt",
        "ZA": "South Africa",
        "ZAF": "South Africa",
        "NG": "Nigeria",
        "NGA": "Nigeria",
        "KE": "Kenya",
        "KEN": "Kenya",
        "MA": "Morocco",
        "MAR": "Morocco",
        "TN": "Tunisia",
        "TUN": "Tunisia",
        "DZ": "Algeria",
        "DZA": "Algeria",
        "GH": "Ghana",
        "GHA": "Ghana",
        "GG": "Guernsey",
        "GGY": "Guernsey",
        "TZ": "Tanzania",
        "TZA": "Tanzania",
        "UG": "Uganda",
        "UGA": "Uganda",
        "ZW": "Zimbabwe",
        "ZWE": "Zimbabwe",
        "ZM": "Zambia",
        "ZMB": "Zambia",
        "MW": "Malawi",
        "MWI": "Malawi",
        "BW": "Botswana",
        "BWA": "Botswana",
        "NA": "Namibia",
        "NAM": "Namibia",
        "SZ": "Eswatini",
        "SWZ": "Eswatini",
        "LS": "Lesotho",
        "LSO": "Lesotho",
        "MZ": "Mozambique",
        "MOZ": "Mozambique",
        "AO": "Angola",
        "AGO": "Angola",
        "AR": "Argentina",
        "ARG": "Argentina",
        "CL": "Chile",
        "CHL": "Chile",
        "CO": "Colombia",
        "COL": "Colombia",
        "PE": "Peru",
        "PER": "Peru",
        "EC": "Ecuador",
        "ECU": "Ecuador",
        "UY": "Uruguay",
        "URY": "Uruguay",
        "PY": "Paraguay",
        "PRY": "Paraguay",
        "BO": "Bolivia",
        "BOL": "Bolivia",
        "VE": "Venezuela",
        "VEN": "Venezuela",
        "GY": "Guyana",
        "GUY": "Guyana",
        "SR": "Suriname",
        "SUR": "Suriname",
        "GF": "French Guiana",
        "GUF": "French Guiana",
        "TH": "Thailand",
        "THA": "Thailand",
        "VN": "Vietnam",
        "VNM": "Vietnam",
        "MY": "Malaysia",
        "MYS": "Malaysia",
        "PH": "Philippines",
        "PHL": "Philippines",
        "ID": "Indonesia",
        "IDN": "Indonesia",
        "BD": "Bangladesh",
        "BGD": "Bangladesh",
        "PK": "Pakistan",
        "PAK": "Pakistan",
        "LK": "Sri Lanka",
        "LKA": "Sri Lanka",
        "MM": "Myanmar",
        "MMR": "Myanmar",
        "KH": "Cambodia",
        "KHM": "Cambodia",
        "LA": "Laos",
        "LAO": "Laos",
        "BN": "Brunei",
        "BRN": "Brunei",
        "TL": "East Timor",
        "TLS": "East Timor",
        "MN": "Mongolia",
        "MNG": "Mongolia",
        "NZ": "New Zealand",
        "NZL": "New Zealand",
        "FJ": "Fiji",
        "FJI": "Fiji",
        "PG": "Papua New Guinea",
        "PNG": "Papua New Guinea",
        "SB": "Solomon Islands",
        "SLB": "Solomon Islands",
        "VU": "Vanuatu",
        "VUT": "Vanuatu",
        "NC": "New Caledonia",
        "NCL": "New Caledonia",
        "PF": "French Polynesia",
        "PYF": "French Polynesia",
        "WS": "Samoa",
        "WSM": "Samoa",
        "TO": "Tonga",
        "TON": "Tonga",
        "TV": "Tuvalu",
        "TUV": "Tuvalu",
        "KI": "Kiribati",
        "KIR": "Kiribati",
        "NR": "Nauru",
        "NRU": "Nauru",
        "PW": "Palau",
        "PLW": "Palau",
        "FM": "Micronesia",
        "FSM": "Micronesia",
        "MH": "Marshall Islands",
        "MHL": "Marshall Islands",
        "CK": "Cook Islands",
        "COK": "Cook Islands",
        "NU": "Niue",
        "NIU": "Niue",
        "TK": "Tokelau",
        "TKL": "Tokelau",
        "AS": "American Samoa",
        "ASM": "American Samoa",
        "GU": "Guam",
        "GUM": "Guam",
        "MP": "Northern Mariana Islands",
        "MNP": "Northern Mariana Islands",
        "PR": "Puerto Rico",
        "PRI": "Puerto Rico",
        "VI": "U.S. Virgin Islands",
        "VIR": "U.S. Virgin Islands",
        "UM": "U.S. Minor Outlying Islands",
        "UMI": "U.S. Minor Outlying Islands",
        "VG": "British Virgin Islands",
        "VGB": "British Virgin Islands",
        "AX": "Åland Islands",
        "ALA": "Åland Islands",
        "JO": "Jordan",
        "JOR": "Jordan",
        "IS": "Iceland",
        "ISL": "Iceland",
        "BS": "Bahamas",
        "BHS": "Bahamas",
        "CR": "Costa Rica",
        "CRI": "Costa Rica",
        "GI": "Gibraltar",
        "GIB": "Gibraltar",
        "CI": "Côte d'Ivoire",
        "CIV": "Côte d'Ivoire",
        "MO": "Macau",
        "MAC": "Macau",
    }

    @classmethod
    def get_country_name_by_code(cls, code):
        if not code:
            return None

        normalized_code = code.upper().strip()
        return cls.COUNTRY_CODE_MAP.get(normalized_code)

    @classmethod
    def reconcile_country_names(cls):
        logger.info("Starting country name reconciliation process")

        updated_count = 0
        not_found_count = 0
        already_named_count = 0
        error_count = 0
        not_found_codes = []

        countries = Country.objects.all()
        total_countries = countries.count()

        logger.info(f"Found {total_countries} countries to process")

        for country in countries:
            try:
                if country.name:
                    already_named_count += 1
                    continue

                if not country.code:
                    logger.warning(f"Country {country.uuid} has no code to reconcile")
                    error_count += 1
                    continue

                country_name = cls.get_country_name_by_code(country.code)

                if country_name:
                    country.name = country_name
                    country.save(update_fields=["name", "updated_at"])
                    updated_count += 1
                    logger.info(f"Updated country {country.code} -> {country_name}")
                else:
                    not_found_count += 1
                    not_found_codes.append(country.code)
                    logger.warning(f"No mapping found for country code: {country.code}")

            except Exception as e:
                error_count += 1
                logger.error(f"Error processing country {country.code}: {str(e)}")

        summary = {
            "total_countries": total_countries,
            "updated_count": updated_count,
            "already_named_count": already_named_count,
            "not_found_count": not_found_count,
            "error_count": error_count,
            "not_found_codes": not_found_codes,
        }

        logger.info(f"Country reconciliation completed: {summary}")

        return summary

    @classmethod
    def reconcile_single_country(cls, country_code):
        try:
            country = Country.objects.get(code=country_code)
            country_name = cls.get_country_name_by_code(country_code)

            if country_name:
                country.name = country_name
                country.save(update_fields=["name", "updated_at"])
                return {
                    "success": True,
                    "message": f"Updated country {country_code} -> {country_name}",
                    "country_name": country_name,
                }
            else:
                return {
                    "success": False,
                    "message": f"No mapping found for country code: {country_code}",
                    "country_name": None,
                }

        except Country.DoesNotExist:
            return {
                "success": False,
                "message": f"Country with code {country_code} not found in database",
                "country_name": None,
            }
        except Exception as e:
            logger.error(f"Error reconciling country {country_code}: {str(e)}")
            return {"success": False, "message": f"Error reconciling country: {str(e)}", "country_name": None}
