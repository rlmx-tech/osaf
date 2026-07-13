"""Seed the database with shark species and sample incidents."""

import asyncio
from datetime import date, time
from decimal import Decimal

from sqlalchemy import select

from app.database import async_session
from app.models.incident import Incident
from app.models.source import IncidentSource
from app.models.species import SharkSpecies
from app.utils.geo import point_from_coords

SPECIES = [
    {
        "common_name": "Great White Shark",
        "scientific_name": "Carcharodon carcharias",
        "family": "Lamnidae",
        "danger_rating": "high",
        "max_size_meters": Decimal("6.1"),
        "notes": "Responsible for most recorded unprovoked attacks on humans. Apex predator found worldwide in cool coastal waters.",
    },
    {
        "common_name": "Tiger Shark",
        "scientific_name": "Galeocerdo cuvier",
        "family": "Carcharhinidae",
        "danger_rating": "high",
        "max_size_meters": Decimal("5.5"),
        "notes": "Second most recorded attacks on humans. Known for indiscriminate diet. Tropical and warm-temperate waters.",
    },
    {
        "common_name": "Bull Shark",
        "scientific_name": "Carcharhinus leucas",
        "family": "Carcharhinidae",
        "danger_rating": "high",
        "max_size_meters": Decimal("3.5"),
        "notes": "Third most recorded attacks. Unique ability to enter freshwater rivers and lakes. Aggressive and territorial.",
    },
    {
        "common_name": "Oceanic Whitetip Shark",
        "scientific_name": "Carcharhinus longimanus",
        "family": "Carcharhinidae",
        "danger_rating": "high",
        "max_size_meters": Decimal("4.0"),
        "notes": "Historically responsible for many open-ocean attacks, particularly shipwreck survivors. Now critically endangered.",
    },
    {
        "common_name": "Shortfin Mako Shark",
        "scientific_name": "Isurus oxyrinchus",
        "family": "Lamnidae",
        "danger_rating": "moderate",
        "max_size_meters": Decimal("4.5"),
        "notes": "Fastest shark species. Most attacks associated with fishing interactions (provoked).",
    },
    {
        "common_name": "Blacktip Shark",
        "scientific_name": "Carcharhinus limbatus",
        "family": "Carcharhinidae",
        "danger_rating": "moderate",
        "max_size_meters": Decimal("2.8"),
        "notes": "Common in Florida surf zone. Responsible for many minor hit-and-run bites, often mistaking hands/feet for fish.",
    },
    {
        "common_name": "Hammerhead Shark (Great)",
        "scientific_name": "Sphyrna mokarran",
        "family": "Sphyrnidae",
        "danger_rating": "moderate",
        "max_size_meters": Decimal("6.1"),
        "notes": "Largest hammerhead species. Few unprovoked attacks recorded. Critically endangered.",
    },
    {
        "common_name": "Blue Shark",
        "scientific_name": "Prionace glauca",
        "family": "Carcharhinidae",
        "danger_rating": "moderate",
        "max_size_meters": Decimal("3.8"),
        "notes": "Most widely distributed shark. Attacks rare but can be persistent. Often involved in boat bite incidents.",
    },
    {
        "common_name": "Nurse Shark",
        "scientific_name": "Ginglymostoma cirratum",
        "family": "Ginglymostomatidae",
        "danger_rating": "low",
        "max_size_meters": Decimal("4.3"),
        "notes": "Bottom-dwelling. Most bites are provoked (stepped on, grabbed). Strong jaw grip but rarely causes serious injury.",
    },
    {
        "common_name": "Lemon Shark",
        "scientific_name": "Negaprion brevirostris",
        "family": "Carcharhinidae",
        "danger_rating": "low",
        "max_size_meters": Decimal("3.4"),
        "notes": "Common in shallow tropical waters. Bites are almost always provoked or related to feeding activities.",
    },
    {
        "common_name": "Caribbean Reef Shark",
        "scientific_name": "Carcharhinus perezi",
        "family": "Carcharhinidae",
        "danger_rating": "moderate",
        "max_size_meters": Decimal("3.0"),
        "notes": "Most common reef shark in the Caribbean. Involved in some dive-related incidents, usually feeding-associated.",
    },
    {
        "common_name": "Bronze Whaler Shark",
        "scientific_name": "Carcharhinus brachyurus",
        "family": "Carcharhinidae",
        "danger_rating": "moderate",
        "max_size_meters": Decimal("3.3"),
        "notes": "Common in temperate waters of southern hemisphere. Notable for attacks off South Africa and Australia.",
    },
    {
        "common_name": "Wobbegong Shark",
        "scientific_name": "Orectolobus maculatus",
        "family": "Orectolobidae",
        "danger_rating": "low",
        "max_size_meters": Decimal("3.2"),
        "notes": "Bottom-dwelling ambush predator. Bites usually from accidental stepping. Common in Australian waters.",
    },
    {
        "common_name": "Grey Reef Shark",
        "scientific_name": "Carcharhinus amblyrhynchos",
        "family": "Carcharhinidae",
        "danger_rating": "moderate",
        "max_size_meters": Decimal("2.6"),
        "notes": "Known threat display before attacking (hunched back, lowered pectoral fins). Common in Indo-Pacific reefs.",
    },
    {
        "common_name": "Spinner Shark",
        "scientific_name": "Carcharhinus brevipinna",
        "family": "Carcharhinidae",
        "danger_rating": "low",
        "max_size_meters": Decimal("3.0"),
        "notes": "Often confused with blacktip shark. Known for spinning leaps. Minor bite incidents in Florida surf zone.",
    },
]

INCIDENTS = [
    {
        "case_number": "OSAF-2024-0001",
        "incident_date": date(2024, 6, 7),
        "incident_time": time(10, 30),
        "location_description": "New Smyrna Beach, near the inlet",
        "country": "United States",
        "state_province": "Florida",
        "county_region": "Volusia County",
        "body_of_water": "Atlantic Ocean",
        "longitude": -80.9270,
        "latitude": 29.0258,
        "classification": "unprovoked",
        "classification_subtype": "hit_and_run",
        "shark_species_suspected": "Carcharhinus limbatus",
        "species_identification_method": "witness",
        "victim_activity": "surfing",
        "victim_injury_severity": "minor",
        "victim_injury_description": "Lacerations to right foot, approximately 5 stitches required",
        "victim_age": 23,
        "victim_sex": "male",
        "fatal": False,
        "description": "Surfer was sitting on board waiting for waves when bitten on the foot. Shark immediately released and swam away. Consistent with mistaken identity hit-and-run typical of the area.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Surfer bitten by shark at New Smyrna Beach",
                "source_publisher": "Daytona Beach News-Journal",
                "source_date": date(2024, 6, 7),
            }
        ],
    },
    {
        "case_number": "OSAF-2024-0002",
        "incident_date": date(2024, 7, 15),
        "incident_time": time(14, 15),
        "location_description": "Jeffreys Bay, Supertubes section",
        "country": "South Africa",
        "state_province": "Eastern Cape",
        "body_of_water": "Indian Ocean",
        "longitude": 24.9318,
        "latitude": -34.0488,
        "classification": "unprovoked",
        "classification_subtype": "bump_and_bite",
        "shark_species_confirmed": "Carcharodon carcharias",
        "species_identification_method": "photo",
        "victim_activity": "surfing",
        "victim_injury_severity": "severe",
        "victim_injury_description": "Deep lacerations to left thigh, significant tissue damage requiring surgery",
        "victim_age": 31,
        "victim_sex": "male",
        "fatal": False,
        "description": "Surfer reported being bumped before the shark bit down on his leg. Nearby surfers helped him to shore. Emergency services responded quickly. Shark identified as a great white from photos taken by other surfers.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Shark attack at Jeffreys Bay injures surfer",
                "source_publisher": "IOL News",
                "source_date": date(2024, 7, 15),
            },
            {
                "source_type": "government_report",
                "source_title": "KZN Sharks Board incident report",
                "source_publisher": "KwaZulu-Natal Sharks Board",
                "source_date": date(2024, 7, 16),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0003",
        "incident_date": date(2024, 3, 22),
        "incident_time": time(7, 45),
        "location_description": "Bondi Beach, south end near rocks",
        "country": "Australia",
        "state_province": "New South Wales",
        "body_of_water": "Tasman Sea",
        "longitude": 151.2743,
        "latitude": -33.8915,
        "classification": "unprovoked",
        "classification_subtype": "hit_and_run",
        "shark_species_suspected": "Carcharhinus brachyurus",
        "species_identification_method": "expert",
        "victim_activity": "swimming",
        "victim_injury_severity": "moderate",
        "victim_injury_description": "Bite wound to lower left leg, lacerations and puncture wounds",
        "victim_age": 45,
        "victim_sex": "female",
        "fatal": False,
        "description": "Early morning swimmer bitten while swimming approximately 50m from shore. Lifeguards assisted victim to beach and applied first aid. Suspected bronze whaler based on bite pattern.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Swimmer bitten by shark at Bondi Beach",
                "source_publisher": "Sydney Morning Herald",
                "source_date": date(2024, 3, 22),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0004",
        "incident_date": date(2024, 9, 3),
        "location_description": "Réunion Island, Saint-Leu coast",
        "country": "France",
        "state_province": "Réunion",
        "body_of_water": "Indian Ocean",
        "longitude": 55.2847,
        "latitude": -21.1667,
        "classification": "unprovoked",
        "classification_subtype": "sneak",
        "shark_species_confirmed": "Carcharhinus leucas",
        "species_identification_method": "tooth_fragment",
        "victim_activity": "surfing",
        "victim_injury_severity": "fatal",
        "victim_age": 28,
        "victim_sex": "male",
        "fatal": True,
        "description": "Surfer attacked without warning in an area known for bull shark activity. Despite rapid rescue by nearby surfers and emergency medical response, the victim succumbed to injuries. Tooth fragment recovered confirmed bull shark.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Fatal shark attack off Réunion Island",
                "source_publisher": "France 24",
                "source_date": date(2024, 9, 3),
            },
            {
                "source_type": "government_report",
                "source_title": "Préfecture de La Réunion incident report",
                "source_publisher": "Préfecture de La Réunion",
                "source_date": date(2024, 9, 4),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0005",
        "incident_date": date(2024, 5, 18),
        "incident_time": time(16, 0),
        "location_description": "Makena Beach, near rocks at south end",
        "country": "United States",
        "state_province": "Hawaii",
        "body_of_water": "Pacific Ocean",
        "longitude": -156.4428,
        "latitude": 20.6301,
        "classification": "unprovoked",
        "classification_subtype": "hit_and_run",
        "shark_species_suspected": "Galeocerdo cuvier",
        "species_identification_method": "witness",
        "victim_activity": "snorkeling",
        "victim_injury_severity": "moderate",
        "victim_injury_description": "Bite to left forearm, deep lacerations requiring surgery",
        "victim_age": 52,
        "victim_sex": "female",
        "fatal": False,
        "description": "Snorkeler bitten while observing reef fish in approximately 3 meters of water. Shark approached from below and bit once before departing. Witnesses described a large tiger shark approximately 3-4 meters.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Snorkeler bitten by shark off Maui coast",
                "source_publisher": "Maui News",
                "source_date": date(2024, 5, 18),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0006",
        "incident_date": date(2024, 8, 10),
        "incident_time": time(11, 0),
        "location_description": "Recife, Boa Viagem Beach",
        "country": "Brazil",
        "state_province": "Pernambuco",
        "body_of_water": "Atlantic Ocean",
        "longitude": -34.8868,
        "latitude": -8.1235,
        "classification": "unprovoked",
        "classification_subtype": "bump_and_bite",
        "shark_species_confirmed": "Carcharhinus leucas",
        "species_identification_method": "expert",
        "victim_activity": "swimming",
        "victim_injury_severity": "severe",
        "victim_injury_description": "Severe lacerations to both legs, emergency surgery required",
        "victim_age": 19,
        "victim_sex": "male",
        "fatal": False,
        "description": "Swimmer attacked in waist-deep water in an area with posted shark warnings. Recife is known for high bull shark activity due to nearby port construction displacing sharks. Victim pulled to shore by beachgoers.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Shark attack at Recife beach injures teenager",
                "source_publisher": "G1 Globo",
                "source_date": date(2024, 8, 10),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0007",
        "incident_date": date(2024, 4, 12),
        "incident_time": time(9, 30),
        "location_description": "Port St Johns, Second Beach",
        "country": "South Africa",
        "state_province": "Eastern Cape",
        "body_of_water": "Indian Ocean",
        "longitude": 29.5453,
        "latitude": -31.6248,
        "classification": "unprovoked",
        "classification_subtype": "sneak",
        "shark_species_confirmed": "Carcharhinus leucas",
        "species_identification_method": "expert",
        "victim_activity": "swimming",
        "victim_injury_severity": "fatal",
        "victim_age": 22,
        "victim_sex": "male",
        "fatal": True,
        "description": "Second Beach at Port St Johns has one of the highest fatality rates in the world, with multiple fatal attacks attributed to bull sharks in the Mzimvubu River estuary. Victim attacked while swimming with friends.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Fatal shark attack at Port St Johns",
                "source_publisher": "Daily Dispatch",
                "source_date": date(2024, 4, 12),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0008",
        "incident_date": date(2024, 11, 5),
        "incident_time": time(13, 45),
        "location_description": "Bahamas, Nassau, Clifton Heritage Beach",
        "country": "Bahamas",
        "body_of_water": "Atlantic Ocean",
        "longitude": -77.5436,
        "latitude": 25.0132,
        "classification": "provoked",
        "shark_species_confirmed": "Carcharhinus perezi",
        "species_identification_method": "photo",
        "victim_activity": "diving",
        "victim_injury_severity": "moderate",
        "victim_injury_description": "Bite to right hand during shark feeding dive",
        "victim_age": 35,
        "victim_sex": "male",
        "fatal": False,
        "description": "Tourist on a commercial shark feeding dive bitten on the hand while feeding Caribbean reef sharks. Classified as provoked due to deliberate feeding interaction.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Tourist bitten during shark dive in Bahamas",
                "source_publisher": "Nassau Guardian",
                "source_date": date(2024, 11, 5),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0009",
        "incident_date": date(2024, 2, 28),
        "location_description": "Western Australia, Esperance coast",
        "country": "Australia",
        "state_province": "Western Australia",
        "body_of_water": "Southern Ocean",
        "longitude": 121.8913,
        "latitude": -33.8614,
        "classification": "boat_bite",
        "provocation_subtype": "unprovoked",
        "shark_species_confirmed": "Carcharodon carcharias",
        "species_identification_method": "witness",
        "shark_size_estimate": "4-5 meters",
        "victim_activity": "fishing",
        "victim_injury_severity": "no_injury",
        "fatal": False,
        "description": "Great white shark bit the stern of a 4.5m aluminium fishing boat near Esperance. Shark circled the boat several times before biting the outboard motor housing. No one was injured. Fishermen returned to port immediately.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Great white attacks fishing boat off Esperance",
                "source_publisher": "ABC News Australia",
                "source_date": date(2024, 2, 28),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0010",
        "incident_date": date(2024, 7, 1),
        "incident_time": time(8, 15),
        "location_description": "Outer Banks, Cape Hatteras",
        "country": "United States",
        "state_province": "North Carolina",
        "body_of_water": "Atlantic Ocean",
        "longitude": -75.5243,
        "latitude": 35.2296,
        "classification": "unprovoked",
        "classification_subtype": "hit_and_run",
        "shark_species_suspected": "Carcharhinus limbatus",
        "species_identification_method": "unknown",
        "victim_activity": "wading",
        "victim_injury_severity": "minor",
        "victim_injury_description": "Small bite to left ankle, minor lacerations",
        "victim_age": 12,
        "victim_sex": "female",
        "fatal": False,
        "description": "Child wading in knee-deep water felt a bite on her ankle. Shark was not seen. Wound pattern consistent with small blacktip shark. Treated at local urgent care, no stitches required.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Child bitten by shark at Cape Hatteras",
                "source_publisher": "Outer Banks Voice",
                "source_date": date(2024, 7, 1),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0011",
        "incident_date": date(2024, 12, 14),
        "location_description": "Red Sea, Marsa Alam coast",
        "country": "Egypt",
        "body_of_water": "Red Sea",
        "longitude": 34.9060,
        "latitude": 25.0676,
        "classification": "unprovoked",
        "classification_subtype": "sneak",
        "shark_species_suspected": "Carcharhinus longimanus",
        "species_identification_method": "witness",
        "victim_activity": "snorkeling",
        "victim_injury_severity": "fatal",
        "victim_age": 44,
        "victim_sex": "male",
        "fatal": True,
        "description": "Tourist attacked while snorkeling near a reef. Witnesses described an oceanic whitetip shark. The Red Sea has seen increased shark incidents in recent years, particularly involving oceanic whitetips near popular tourist areas.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Fatal shark attack in Red Sea near Marsa Alam",
                "source_publisher": "Egypt Independent",
                "source_date": date(2024, 12, 14),
            },
            {
                "source_type": "government_report",
                "source_title": "Egyptian Ministry of Environment statement",
                "source_publisher": "Ministry of Environment",
                "source_date": date(2024, 12, 15),
            },
        ],
    },
    {
        "case_number": "OSAF-2024-0012",
        "incident_date": date(2024, 6, 22),
        "incident_time": time(17, 30),
        "location_description": "New Smyrna Beach, Ponce Inlet area",
        "country": "United States",
        "state_province": "Florida",
        "county_region": "Volusia County",
        "body_of_water": "Atlantic Ocean",
        "longitude": -80.9175,
        "latitude": 29.0785,
        "classification": "unprovoked",
        "classification_subtype": "hit_and_run",
        "shark_species_suspected": "Carcharhinus brevipinna",
        "species_identification_method": "unknown",
        "victim_activity": "surfing",
        "victim_injury_severity": "minor",
        "victim_injury_description": "Small lacerations to right hand",
        "victim_age": 17,
        "victim_sex": "male",
        "fatal": False,
        "description": "Teenage surfer bitten on the hand while paddling. New Smyrna Beach (Volusia County) consistently records the most shark bites worldwide, earning it the unofficial title of 'Shark Bite Capital of the World.' Most incidents are minor hit-and-run bites.",
        "verification_status": "verified",
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Another shark bite reported at New Smyrna Beach",
                "source_publisher": "Daytona Beach News-Journal",
                "source_date": date(2024, 6, 22),
            },
        ],
    },
]


async def seed() -> None:
    async with async_session() as session:
        # Check if already seeded
        existing = (await session.execute(
            select(SharkSpecies).limit(1)
        )).scalar_one_or_none()

        if existing:
            print("Database already seeded, skipping.")
            return

        # Seed species
        for sp in SPECIES:
            session.add(SharkSpecies(**sp))
        print(f"Seeded {len(SPECIES)} shark species.")

        # Seed incidents
        for inc_data in INCIDENTS:
            sources_data = inc_data.pop("sources", [])
            lon = inc_data.pop("longitude", None)
            lat = inc_data.pop("latitude", None)

            incident = Incident(**inc_data)
            if lon is not None and lat is not None:
                incident.coordinates = point_from_coords(lon, lat)

            for src in sources_data:
                incident.sources.append(IncidentSource(**src))

            session.add(incident)

        print(f"Seeded {len(INCIDENTS)} sample incidents.")
        await session.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
