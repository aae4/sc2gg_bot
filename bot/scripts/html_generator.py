import sys
import sc2reader
import spawningtool.parser
import operator
from itertools import groupby
import base64
import os.path
from git import Repo
import json
import numpy as np
import pandas as pd
# import zephyrus_sc2_parser
from zephyrus_sc2_parser import parse_replay
from datetime import datetime
from PIL import Image

from configparser import ConfigParser
# parse config
config = ConfigParser()
config.read('../../config.ini')
SC2PAGES_PATH = config.get('project', 'sc2pages_path').strip('\'')
PAGES_URL = config.get('project', 'pages_url').strip('\'')
PROJECT_PATH = config.get('project', 'project_path').strip('\'')
SAVE_ICONS_PATH = config.get('project', 'save_icons_path').strip('\'')
ICON_PATH = config.get('project', 'icon_path').strip('\'')
STORE_REPLAYS_COUNT = int(config.get('project', 'store_replays_count').strip('\''))

# ruby hash for maps and images
# {:"16-Bit SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/cd/16-Bit_SC2_Map1.jpg", :"2000 Atmospheres SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/6a/2000_Atmospheres_SC2_Map1.jpg", :"AbandonedCamp SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/3c/AbandonedCamp_SC2_Map1.jpg", :"AbandonedParish SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/5f/AbandonedParish_SC2_Map1.jpg", :"Abiogenesis SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/9c/Abiogenesis_SC2_Map1.jpg", :"Abyss SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/a9/Abyss_SC2_Map1.jpg", :"Abyssal Reef SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/30/Abyssal_Reef_SC2_Map1.jpg", :"AcidPlant SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b4/AcidPlant_SC2_Map1.jpg", :"Acolyte SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/6d/Acolyte_SC2_Map1.jpg", :"Acropolis SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b5/Acropolis_SC2_Map1.jpg", :"Aftermath SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/ea/Aftermath_SC2_Map1.jpg", :"AgriaValley SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/76/AgriaValley_SC2_Map1.jpg", :"AiurChef SC2 DevLogo1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b2/AiurChef_SC2_DevLogo1.jpg", :"AkilonFlats SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/2d/AkilonFlats_SC2_Map1.jpg", :"AkilonWastes SC2-HotS Art1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/16/AkilonWastes_SC2-HotS_Art1.jpg", :"AlterzimStronghold SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/79/AlterzimStronghold_SC2_Map1.jpg", :"Anaconda SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/5c/Anaconda_SC2_Map1.jpg", :"AntigaShipyard SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/c6/AntigaShipyard_SC2_Map1.jpg", :"Apotheosis SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/8a/Apotheosis_SC2_Map1.jpg", :"ArakanCitadel SC2 Map1.png"=>"https://static.wikia.nocookie.net/starcraft/images/1/14/ArakanCitadel_SC2_Map1.png", :"ArcticDream SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/c5/ArcticDream_SC2_Map1.jpg", :"ArcticGates SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/20/ArcticGates_SC2_Map1.jpg", :"AridPlateau SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/28/AridPlateau_SC2_Map1.jpg", :"AridWastes SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/a3/AridWastes_SC2_Map1.jpg", :"AscensiontoAiur SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/55/AscensiontoAiur_SC2_Map1.jpg", :"AsperMountain SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/3d/AsperMountain_SC2_Map1.jpg", :"AtlasStation SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/58/AtlasStation_SC2_Map1.jpg", :"AugustineFalls SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/8d/AugustineFalls_SC2_Map1.jpg", :"Automaton SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/9e/Automaton_SC2_Map1.jpg", :"AvalonLabs SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b2/AvalonLabs_SC2_Map1.jpg", :"Backcountry SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/26/Backcountry_SC2_Map1.jpg", :"Backwater SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/cb/Backwater_SC2_Map1.jpg", :"BackwaterComplex SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/7a/BackwaterComplex_SC2_Map1.jpg", :"BackwaterGulch SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/e2/BackwaterGulch_SC2_Map1.jpg", :"BastionoftheConclave SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/f/f6/BastionoftheConclave_SC2_Map1.jpg", :"BattleontheBoardwalk SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/aa/BattleontheBoardwalk_SC2_Map1.jpg", :"Beckett Industries SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/97/Beckett_Industries_SC2_Map1.jpg", :"Bel'ShirVestige SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/ac/Bel%27ShirVestige_SC2_Map1.jpg", :"Bel'shirWinter SC2 Rend1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/ed/Bel%27shirWinter_SC2_Rend1.jpg", :"Blackburn SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/53/Blackburn_SC2_Map1.jpg", :"Blackfrost Extraction SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/5b/Blackfrost_Extraction_SC2_Map1.jpg", :"BlackSite2E SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/f/f4/BlackSite2E_SC2_Map1.jpg", :"BlisteringSands SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/ed/BlisteringSands_SC2_Map1.jpg", :"BloodBoil SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/83/BloodBoil_SC2_Map1.jpg", :"Blueshift SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/ba/Blueshift_SC2_Map1.jpg", :"BoneTemple SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/76/BoneTemple_SC2_Map1.jpg", :"Bridgehead SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/37/Bridgehead_SC2_Map1.jpg", :"Bulken SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/3a/Bulken_SC2_Map1.jpg", :"BurialGrounds SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/93/BurialGrounds_SC2_Map1.jpg", :"BurningTides SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/f/f9/BurningTides_SC2_Map1.jpg", :"BurriedCaverns SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/33/BurriedCaverns_SC2_Map1.jpg", :"CactusValley SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/e2/CactusValley_SC2_Map1.jpg", :"CalmBeforetheStorm SC2 Rend1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/ed/CalmBeforetheStorm_SC2_Rend1.jpg", :"CanyonofTribulation SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/51/CanyonofTribulation_SC2_Map1.jpg", :"Catallena SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/4/43/Catallena_SC2_Map1.jpg", :"Catalyst SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/97/Catalyst_SC2_Map1.jpg", :"CelestialBastion SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/76/CelestialBastion_SC2_Map1.jpg", :"CentralProtocol SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b4/CentralProtocol_SC2_Map1.jpg", :"CeruleanFall SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/5a/CeruleanFall_SC2_Map1.jpg", :"CinderFortress SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/f/ff/CinderFortress_SC2_Map1.jpg", :"CloudKingdom SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/0/01/CloudKingdom_SC2_Map1.jpg", :"Coda SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/8d/Coda_SC2_Map1.jpg", :"Colony426 SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/0/0f/Colony426_SC2_Map1.jpg", :"Concord SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/1d/Concord_SC2_Map1.jpg", :"CondemnedRidge SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/d2/CondemnedRidge_SC2_Map1.jpg", :"Conduit SC2 LotV Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/cc/Conduit_SC2_LotV_Map1.jpg", :"Crevasse SC2 Rend1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/99/Crevasse_SC2_Rend1.jpg", :"CrookedMaw SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/5b/CrookedMaw_SC2_Map1.jpg", :"Crossfire SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/3e/Crossfire_SC2_Map1.jpg", :"CrypticFortress SC2 LotV Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/9e/CrypticFortress_SC2_LotV_Map1.jpg", :"CrystalPools SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/af/CrystalPools_SC2_Map1.jpg", :"CyberForest SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/0/01/CyberForest_SC2_Map1.jpg", :"DarknessSanctuary SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/f/fb/DarknessSanctuary_SC2_Map1.jpg", :"DashandTerminal SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/85/DashandTerminal_SC2_Map1.jpg", :"Daybreak SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/80/Daybreak_SC2_Map1.jpg", :"Daybreak SC2 Rend1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/14/Daybreak_SC2_Rend1.jpg", :"Dead of Night SC2 Map1.png"=>"https://static.wikia.nocookie.net/starcraft/images/0/07/Dead_of_Night_SC2_Map1.png", :"DeadlockRidge SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/0/05/DeadlockRidge_SC2_Map1.jpg", :"Deadwing SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/9d/Deadwing_SC2_Map1.jpg", :"Deathaura SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/32/Deathaura_SC2_Map1.jpg", :"DebrisField SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/98/DebrisField_SC2_Map1.jpg", :"DefendersLanding SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/63/DefendersLanding_SC2_Map1.jpg", :"DeltaQuadrant SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/62/DeltaQuadrant_SC2_Map1.jpg", :"DerelictWatcher SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/89/DerelictWatcher_SC2_Map1.jpg", :"DesertOasis SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/9f/DesertOasis_SC2_Map1.jpg", :"DesertRefuge SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/0/01/DesertRefuge_SC2_Map1.jpg", :"DesolateStronghold SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/cd/DesolateStronghold_SC2_Map1.jpg", :"DigSite SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/da/DigSite_SC2_Map1.jpg", :"DirtSide SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/c4/DirtSide_SC2_Map1.jpg", :"DiscoBloodbath SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/77/DiscoBloodbath_SC2_Map1.jpg", :"DiscordIV SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/6a/DiscordIV_SC2_Map1.jpg", :"DistantPlane SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/13/DistantPlane_SC2_Map1.jpg", :"District10 SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/df/District10_SC2_Map1.jpg", :"Divergence SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/37/Divergence_SC2_Map1.jpg", :"DoraelusHills SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/ab/DoraelusHills_SC2_Map1.jpg", :"DualSight SC2 Rend1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/a7/DualSight_SC2_Rend1.jpg", :"DuskTowers SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/36/DuskTowers_SC2_Map1.jpg", :"DustyGorge SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/13/DustyGorge_SC2_Map1.jpg", :"Eastwatch SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/7a/Eastwatch_SC2_Map1.jpg", :"Echo SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/cc/Echo_SC2_Map1.jpg", :"Efflorescence SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/52/Efflorescence_SC2_Map1.jpg", :"Elysium SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/7d/Elysium_SC2_Map1.jpg", :"EmeraldCity SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/36/EmeraldCity_SC2_Map1.jpg", :"EntombedValley SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/81/EntombedValley_SC2_Map1.jpg", :"Ephemeron SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/1b/Ephemeron_SC2_Map1.jpg", :"EternalEmpire SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/74/EternalEmpire_SC2_Map1.jpg", :"EternalScar SC2 Map1.JPG"=>"https://static.wikia.nocookie.net/starcraft/images/1/19/EternalScar_SC2_Map1.JPG", :"EverDream SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b4/EverDream_SC2_Map1.jpg", :"ExpeditionLost SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/ee/ExpeditionLost_SC2_Map1.jpg", :"Extinction SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/74/Extinction_SC2_Map1.jpg", :"FalloutZone SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/ed/FalloutZone_SC2_Map1.jpg", :"FieldsofShazir SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/86/FieldsofShazir_SC2_Map1.jpg", :"Flashback SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/39/Flashback_SC2_Map1.jpg", :"FloodedCity SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/66/FloodedCity_SC2_Map1.jpg", :"ForbiddenPlanet SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/4/4c/ForbiddenPlanet_SC2_Map1.jpg", :"ForbiddenSanctuary SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/12/ForbiddenSanctuary_SC2_Map1.jpg", :"ForgottenSanctuary SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b8/ForgottenSanctuary_SC2_Map1.jpg", :"Fortitude SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/25/Fortitude_SC2_Map1.jpg", :"FossilQuarry SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/65/FossilQuarry_SC2_Map1.jpg", :"FoxtrotLabs SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/e0/FoxtrotLabs_SC2_Map1.jpg", :"Fracture SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/4/4e/Fracture_SC2_Map1.jpg", :"FracturedGlacier SC2-HotS Art1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/cb/FracturedGlacier_SC2-HotS_Art1.jpg", :"Frontier SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/d2/Frontier_SC2_Map1.jpg", :"Frost SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/d0/Frost_SC2_Map1.jpg", :"FrozenFields SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/99/FrozenFields_SC2_Map1.jpg", :"FrozenTemple SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/6a/FrozenTemple_SC2_Map1.jpg", :"GalacticProcess SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/3b/GalacticProcess_SC2_Map1.jpg", :"Garden of Shadows SC2 LotV Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/4/4a/Garden_of_Shadows_SC2_LotV_Map1.jpg", :"GeosyncQuarry SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/f/fe/GeosyncQuarry_SC2_Map1.jpg", :"GoldenWall SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/29/GoldenWall_SC2_Map1.jpg", :"GraystoneRavine SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b4/GraystoneRavine_SC2_Map1.jpg", :"GreenAcres SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/f/ff/GreenAcres_SC2_Map1.jpg", :"Gutterhulk SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/56/Gutterhulk_SC2_Map1.jpg", :"GwangalliBeach SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/92/GwangalliBeach_SC2_Map1.jpg", :"HabitationStation SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/36/HabitationStation_SC2_Map1.jpg", :"Halcyon SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/14/Halcyon_SC2_Map1.jpg", :"HavensFall SC2-WoL Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/d8/HavensFall_SC2-WoL_Map1.jpg", :"HeavyArtillery SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/94/HeavyArtillery_SC2_Map1.jpg", :"HeavyRain SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/51/HeavyRain_SC2_Map1.jpg", :"HiddenCaves SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/18/HiddenCaves_SC2_Map1.jpg", :"HighGround SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/6a/HighGround_SC2_Map1.jpg", :"HighOrbit SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/73/HighOrbit_SC2_Map1.jpg", :"HillsofPeshkov SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/82/HillsofPeshkov_SC2_Map1.jpg", :"HonorGrounds SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/d9/HonorGrounds_SC2_Map1.jpg", :"HowlingPeak SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/57/HowlingPeak_SC2_Map1.jpg", :"HowlingPeaks SC2-HotS Art1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/95/HowlingPeaks_SC2-HotS_Art1.jpg", :"HuntingGround SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/58/HuntingGround_SC2_Map1.jpg", :"Ice and Chrome SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/0/0d/Ice_and_Chrome_SC2_Map1.jpg", :"IceCliffs SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/a5/IceCliffs_SC2_Map1.jpg", :"IncinerationZone SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/4/4e/IncinerationZone_SC2_Map1.jpg", :"InfernoPools SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/0/0a/InfernoPools_SC2_Map1.jpg", :"Infestation SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/8c/Infestation_SC2_Map1.jpg", :"Interloper SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/bd/Interloper_SC2_Map1.jpg", :"Invader SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/57/Invader_SC2_Map1.jpg", :"IsleofSlaughter SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/0/07/IsleofSlaughter_SC2_Map1.jpg", :"Jagannatha SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/9c/Jagannatha_SC2_Map1.jpg", :"JungleBasin SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/4/43/JungleBasin_SC2_Map1.jpg", :"JungleDepths SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/4/49/JungleDepths_SC2_Map1.jpg", :"JunkYard SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/d7/JunkYard_SC2_Map1.jpg", :"KairosJunction SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/52/KairosJunction_SC2_Map1.jpg", :"KatherineSquare SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/79/KatherineSquare_SC2_Map1.jpg", :"KerrigansWrath SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/a4/KerrigansWrath_SC2_Map1.jpg", :"KhaydarinDepths SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/16/KhaydarinDepths_SC2_Map1.jpg", :"KimeranRefuge SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/e8/KimeranRefuge_SC2_Map1.jpg", :"KingsCove SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/92/KingsCove_SC2_Map1.jpg", :"KingSejongStation SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/4/47/KingSejongStation_SC2_Map1.jpg", :"KlontasMire SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/8/88/KlontasMire_SC2_Map1.jpg", :"KorhalCarnageKnockout SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/c7/KorhalCarnageKnockout_SC2_Map1.jpg", :"KorhalCity SC2-HotS Art1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/7/7a/KorhalCity_SC2-HotS_Art1.jpg", :"KorhalCompound SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/12/KorhalCompound_SC2_Map1.jpg", :"KorhalSkyIsland SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/55/KorhalSkyIsland_SC2_Map1.jpg", :"KulasRavine SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/cc/KulasRavine_SC2_Map1.jpg", :"Last Impact SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/50/Last_Impact_SC2_Map1.jpg", :"LastRemnant SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/66/LastRemnant_SC2_Map1.jpg", :"LavaFlow SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/67/LavaFlow_SC2_Map1.jpg", :"Left2Die SC2 DevLogo1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/50/Left2Die_SC2_DevLogo1.jpg", :"Lightshade SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/62/Lightshade_SC2_Map1.jpg", :"LostTemple SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/38/LostTemple_SC2_Map1.jpg", :"LunarColonyV SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/3/32/LunarColonyV_SC2_Map1.jpg", :"MagmaCore SC2 LotV Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/1a/MagmaCore_SC2_LotV_Map1.jpg", :"MagmaMines SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/97/MagmaMines_SC2_Map1.jpg", :"MechDepot SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/e9/MechDepot_SC2_Map1.jpg", :"Megaton SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/b1/Megaton_SC2_Map1.jpg", :"Mementos SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/6/6e/Mementos_SC2_Map1.jpg", :"MerryGoRound SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/e1/MerryGoRound_SC2_Map1.jpg", :"Metalopolis SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/5c/Metalopolis_SC2_Map1.jpg", :"Metropolis SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/d/de/Metropolis_SC2_Map1.jpg", :"Metropolis SC2 Rend1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/e9/Metropolis_SC2_Rend1.jpg", :"MinerEvacuation SC2 Map1.png"=>"https://static.wikia.nocookie.net/starcraft/images/7/79/MinerEvacuation_SC2_Map1.png", :"MoebiusFacilityXX1 SC2 LotV Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/f/f1/MoebiusFacilityXX1_SC2_LotV_Map1.jpg", :"MoltenCrater SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/b/bf/MoltenCrater_SC2_Map1.jpg", :"MoltenTemple SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/2b/MoltenTemple_SC2_Map1.jpg", :"MonlythRidge SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/5/51/MonlythRidge_SC2_Map1.jpg", :"Monsoon SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/a/ae/Monsoon_SC2_Map1.jpg", :"MoonlightMadness SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/24/MoonlightMadness_SC2_Map1.jpg", :"Multiprocessor SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/9/90/Multiprocessor_SC2_Map1.jpg", :"Nekodrec SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/c/cb/Nekodrec_SC2_Map1.jpg", :"Neo Seoul SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/2/2c/Neo_Seoul_SC2_Map1.jpg", :"NeonVioletSquare SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/e/ea/NeonVioletSquare_SC2_Map1.jpg", :"NeoPlanetS SC2 Map1.jpg"=>"https://static.wikia.nocookie.net/starcraft/images/1/14/NeoPlanetS_SC2_Map1.jpg"}

# SAVE_ICONS_PATH = "/Users/abazov/workspace/unknown/sc2/sc2gg_bot/icons"
# ICON_PATH = "/Users/abazov/workspace/unknown/sc2/sc2gg_bot/icons"

# SC2PAGES_PATH = '/Users/abazov/workspace/unknown/sc2/sc2pages'
# PAGES_URL = 'https://aae4.github.io/pages/sc2'

# PROJECT_PATH = '/Users/abazov/workspace/unknown/sc2/sc2gg_bot'
# SAVE_ICONS_PATH = '/Users/abazov/workspace/unknown/sc2/sc2pages/resources/sc2/icons'
# ICON_PATH = './resources/sc2/icons'
# STORE_REPLAYS_COUNT = 8

# SC2PAGES_PATH = settings.SC2PAGES_PATH
# PAGES_URL = settings.PAGES_URL

# PROJECT_PATH = settings.PROJECT_PATH
# SAVE_ICONS_PATH = settings.SAVE_ICONS_PATH
# ICON_PATH = settings.ICON_PATH
# STORE_REPLAYS_COUNT = settings.STORE_REPLAYS_COUNT


RACE_MAP = {
  '저그': 'Zerg',
  '异虫': 'Zerg',
  '蟲族': 'Zerg',
  'Зерги': 'Zerg',
  'Zerg': 'Zerg',
  '테란': 'Terran',
  '人類': 'Terran',
  '人类': 'Terran',
  'Terraner': 'Terran',
  'Терраны': 'Terran',
  'Terran': 'Terran',
  '프로토스': 'Protoss',
  '神族': 'Protoss',
  'Protosi': 'Protoss',
  '星灵': 'Protoss',
  'Протоссы': 'Protoss',
  'Protoss': 'Protoss',
}

MAP_ICONS = {
  '2000 атмосфер РВ': f'{ICON_PATH}/maps/2000_Atmospheres.jpg',
  'Берлинград РВ': f'{ICON_PATH}/maps/Berlingrad.jpg',
  'Беккетт Индастриз РВ': f'{ICON_PATH}/maps/Beckett_Industries.jpg',
  'Блэкберн РВ': f'{ICON_PATH}/maps/Blackburn.jpg',
  'Пытливые умы РВ': f'{ICON_PATH}/maps/Curious_Minds.jpg',
  'Блестящий пепел РВ': f'{ICON_PATH}/maps/Glittering_Ashes.jpg',
  'Проводка РВ': f'{ICON_PATH}/maps/Hardwire.jpg',
  'Гордость Алтариса РВ': f'{ICON_PATH}/maps/Pride_of_Altaris.jpg',


  '2000 Atmospheres LE': f'{ICON_PATH}/maps/2000_Atmospheres.jpg',
  'Berlingrad LE': f'{ICON_PATH}/maps/Berlingrad.jpg',
  'Beckett Industries LE': f'{ICON_PATH}/maps/Beckett_Industries.jpg',
  'Blackburn LE': f'{ICON_PATH}/maps/Blackburn.jpg',
  'Curious Minds LE': f'{ICON_PATH}/maps/Curious_Minds.jpg',
  'Glittering Ashes LE': f'{ICON_PATH}/maps/Glittering_Ashes.jpg',
  'Hardwire LE': f'{ICON_PATH}/maps/Hardwire.jpg',
  'Pride of Altaris LE': f'{ICON_PATH}/maps/Pride_of_Altaris.jpg'
}


RACE_URL = {
  'Zerg': f'{ICON_PATH}/races/ZergIcon.png',
  'Protoss': f'{ICON_PATH}/races/ProtossIcon.png',
  'Terran': f'{ICON_PATH}/races/TerranIcon.png'
}

class Exporter:

  def __init__(self, path):
    self.sc2replay = sc2reader.load_replay(path)
    self.init_players()
    self.parsed_result = spawningtool.parser.parse_replay(path, None, None, True)
    self.is_zephir = True
    try:
      self.zreplay = parse_replay(path)
    except Exception as e:
      self.is_zephir = False

    self.base_data = self.get_base_data()
    self.units_for_game_state = self.sc2replay.objects.values()
    update_born_locations(self.units_for_game_state, self.sc2replay)

  def init_players(self):
    self.players = {}
    for player in self.sc2replay.players:
      self.players[player.pid] = player

  def is_valid_replay(self):
    if self.sc2replay.game_type != '1v1':
      self.result = {'status': False, 'message': 'Sorry, only 1v1 games supported'}
      return False
    return True

  def generateHtml(self):
    with open(f'{PROJECT_PATH}/bot/scripts/template/main.html', 'r') as file:
      main_html = file.read()

    with open(f'{PROJECT_PATH}/bot/scripts/template/vue.html', 'r') as file:
      vue_html = file.read()

    data = self.generate_json()

    res = main_html
    res += f"<script>\n  const replay_data = {json.dumps(data)}\n</script>"
    res += vue_html

    replay_name = self.generateReplayName();

    # html_file = open(f"{PROJECT_PATH}/{replay_name}.html", 'w')
    html_file = open(f"{SC2PAGES_PATH}/{replay_name}.html", 'w')
    html_file.write(res)

    return f'{replay_name}.html'

  def run(self):
    try:
      if not self.is_valid_replay(): return

      filename = self.generateHtml()
      self.export_to_git_pages()
      self.cleanup()
      self.result = {'status': True, 'message': 'Report successfully generated', 'filename': filename, 'url': f'{PAGES_URL}/{filename}'}
      return self.result
    except Exception as e:
      self.result = {'status': False, 'message': 'Error', 'url': ''}
      return self.result

  def cleanup(self):
    replays_path = f'{PROJECT_PATH}/files'
    filenames = [entry.name for entry in sorted(os.scandir(replays_path), key=lambda x: x.stat().st_mtime, reverse=True)]
    for filename in filenames[STORE_REPLAYS_COUNT:]:
      filename_relPath = os.path.join(replays_path, filename)
      os.remove(filename_relPath)

    reports_path = f'{SC2PAGES_PATH}/sc2'
    filenames = [entry.name for entry in sorted(os.scandir(reports_path), key=lambda x: x.stat().st_mtime, reverse=True)]
    for filename in filenames[STORE_REPLAYS_COUNT:]:
      filename_relPath = os.path.join(reports_path, filename)
      os.remove(filename_relPath)

  def generate_json(self):
    return {
      'base_data': self.base_data,
      'battles_source': self.generate_battles(),
      'graphs_data': self.graphs_data(),
      'timeline': getTimeline(self.sc2replay, units = self.units_for_game_state)
    }

  def get_base_data(self):
    base_data = self.parsed_result
    base_data['is_zephir'] = self.is_zephir
    base_data['version'] = self.sc2replay.release_string
    base_data['length'] = str(self.sc2replay.game_length)

    for pid in base_data['players'].keys():
      player = base_data['players'][pid]
      player['play_race_url'] =  RACE_URL[RACE_MAP[self.players[pid].play_race]]
      player['url'] = self.players[pid].url

    base_data['map_details'] = self.map_details()

    return base_data

  def map_details(self):
    replay = self.sc2replay
    replay.load_map()
    mini_map_name = f"{replay.map.name}_mini.tga"
    # TODO: uncom
    if not os.path.isfile(f"{SAVE_ICONS_PATH}/maps/{mini_map_name}"):
      mini_map = open(f"{SAVE_ICONS_PATH}/maps/{mini_map_name}", 'wb')
      mini_map.write(replay.map.minimap)
      mini_map.close()
      Image.open(f"{SAVE_ICONS_PATH}/maps/{mini_map_name}").save(f"{SAVE_ICONS_PATH}/maps/{replay.map.name}_mini.png")

    name = replay.map.name
    width = replay.map.map_info.width
    height = replay.map.map_info.height

    # actual_width = replay.map.map_info.camera_right - replay.map.map_info.camera_left
    # actual_height = replay.map.map_info.camera_top - replay.map.map_info.camera_bottom

    return {
      'name': name,
      'width': width,
      'height': height,
      # 'actual_width': actual_width,
      # 'actual_height': actual_height,
      'map_url': MAP_ICONS[self.sc2replay.map_name],
      'mini_map_url': f'{ICON_PATH}/maps/{replay.map.name}.png'
    }

  def export_to_git_pages(self):
    commit_message = 'upload replay'
    try:
      repo = Repo(SC2PAGES_PATH)
      # repo.git.add(update=True)
      repo.git.add(all=True)
      repo.index.commit(commit_message)
      origin = repo.remote(name='origin')
      origin.push()
    except:
      print('Some error occured while pushing the code')

  def generateReplayName(self):
    date = datetime.utcfromtimestamp(self.sc2replay.unix_timestamp).strftime('%Y%m%d%H%M%S')
    return f'{date}_{self.sc2replay.map_name}_{self.sc2replay.players[0].name}_vs_{self.sc2replay.players[1].name}'

  def getEvents(self, name = ''):
    return list({event for event in self.sc2replay.events if name in event.name})

  def summary_data(self):
    if self.is_zephir == False:
      return []

    summary = self.zreplay[3]
    player_ids = [1, 2]

    h = ['name', 'avg_minerals_collection_rate', 'avg_gas_resource_collection_rate', 'avg_minerals_unspent', 'avg_gas_unspent', 'minerals_collected', 'gas_collected', 'apm', 'supply_block', 'workers_killed', 'workers_lost', 'workers_produced']
    res = []

    #TODO: вынести в инит
    # base_data = self.base_data()
    for i in player_ids:
      summ = {}
      summ['name'] = self.base_data['players'][i]['name']
      summ['avg_minerals_collection_rate'] = summary['avg_resource_collection_rate']['minerals'][i]
      summ['avg_gas_resource_collection_rate'] = summary['avg_resource_collection_rate']['gas'][i]
      summ['avg_minerals_unspent'] = summary['avg_unspent_resources']['minerals'][i]
      summ['avg_gas_unspent'] = summary['avg_unspent_resources']['gas'][i]
      summ['minerals_collected'] = summary['resources_collected']['minerals'][i]
      summ['gas_collected'] = summary['resources_collected']['gas'][i]
      summ['apm'] = summary['apm'][i]
      summ['supply_block'] = summary['supply_block'][i]
      summ['workers_killed'] = summary['workers_killed'][i]
      summ['workers_lost'] = summary['workers_lost'][i]
      summ['workers_produced'] = summary['workers_produced'][i]
      res.append(summ)
    return res

  def graphs_data(self):
    units_df_over_time = pd.Series(
        {t:getUnitFeatures(['supply', 'died_at', 'is_army','is_worker','minerals','vespene','player_id'],kwargs={'replay':self.sc2replay, 'time':t}
                                ) for t in range(0,int(frames_to_irl_seconds(self.sc2replay.frames)),5)})

    army_supply = units_df_over_time.apply(lambda x:x[x['is_army'] == True].groupby('player_id')['supply'].sum())
    worker_supply = units_df_over_time.apply(lambda x:x[x['is_worker'] == True].groupby('player_id')['supply'].sum())

    mineral_value = units_df_over_time.apply(lambda x:x.groupby('player_id')['minerals'].sum())
    vespene_value = units_df_over_time.apply(lambda x:x.groupby('player_id')['vespene'].sum())

    time_array = []
    for t in range(0,int(frames_to_irl_seconds(self.sc2replay.frames)),5):
      time_array.append(t)

    army_datasets = []
    workers_datasets = []
    minerals_datasets = []

    player_colors = {
      1: 'red',
      2: 'blue'
    }
    for player in self.sc2replay.players:
      army_datasets.append({
        'label': player.name,
        'backgroundColor': player_colors[player.pid],
        'borderColor': player_colors[player.pid],
        'data': np.nan_to_num(army_supply[player.pid].to_numpy()).tolist()
      })
      workers_datasets.append({
        'label': player.name,
        'backgroundColor': player_colors[player.pid],
        'borderColor': player_colors[player.pid],
        'data': np.nan_to_num(worker_supply[player.pid].to_numpy()).tolist()
      })

    armyChartData = {
      'labels': time_array,
      'datasets': army_datasets
    }

    workersChartData = {
      'labels': time_array,
      'datasets': workers_datasets
    }

    events = self.getEvents(name='PlayerStats')
    attributes = ['frame', 'pid', 'minerals_collection_rate', 'workers_active_count']
    df = pd.DataFrame({feature: [event.__getattribute__(feature) for event in events] for feature in attributes}, columns=attributes)
    df = df.drop_duplicates()
    df['frame'] = df['frame'].apply(frames_to_irl_seconds)
    res = df.sort_values('frame')
    frames_label = res[res["pid"] == 1]['frame'].tolist()
    p1_minerals_collection_rate = res[res["pid"] == 1]['minerals_collection_rate'].tolist()
    p2_minerals_collection_rate = res[res["pid"] == 2]['minerals_collection_rate'].tolist()

    #TODO: вынести в инит
    # base_data = self.base_data()
    minerals_datasets = [
      {
        'label': self.base_data['players'][1]['name'],
        'backgroundColor': player_colors[1],
        'borderColor': player_colors[1],
        'data': p1_minerals_collection_rate
      },
      {
        'label': self.base_data['players'][2]['name'],
        'backgroundColor': player_colors[2],
        'borderColor': player_colors[2],
        'data': p2_minerals_collection_rate
      },
    ]

    mineralsChartData = {
      'labels': frames_label,
      'datasets': minerals_datasets
    }


    p1_workers_active = res[res["pid"] == 1]['workers_active_count'].tolist()
    p2_workers_active = res[res["pid"] == 2]['workers_active_count'].tolist()
    workers_active_datasets = [
      {
        'label': self.base_data['players'][1],
        'backgroundColor': player_colors[1],
        'borderColor': player_colors[1],
        'data': p1_workers_active
      },
      {
        'label': self.base_data['players'][2],
        'backgroundColor': player_colors[2],
        'borderColor': player_colors[2],
        'data': p2_workers_active
      },
    ]

    workersActiveChartData = {
      'labels': frames_label,
      'datasets': workers_active_datasets
    }

    return {
      'summary_data': self.summary_data(),
      'armyChartData': armyChartData,
      'workersChartData': workersChartData,
      'mineralsChartData': mineralsChartData,
      'workersActiveChartData': workersActiveChartData
    }

  def generate_battles(self):
    result_replay = self.parsed_result
    # update player_names for units_lost dicts
    [lost_record.update({'pn': result_replay['players'][1]['name']}) for lost_record in result_replay['players'][1]['unitsLost']]
    [lost_record.update({'pn': result_replay['players'][2]['name']}) for lost_record in result_replay['players'][2]['unitsLost']]

    # concat all units_losts
    units_lost = [*result_replay['players'][1]['unitsLost'], *result_replay['players'][2]['unitsLost']]

    # sort units lost by chronological time
    units_lost.sort(key=lambda x:x['frame'])

    # split into battles
    prev_frame = frames_to_irl_seconds(units_lost[0]['frame'])
    self.battles = []
    current_battle = []

    total_len = len(units_lost)-1
    for index, ul in enumerate(units_lost):
      current_frame = frames_to_irl_seconds(ul['frame'])
      if current_frame - prev_frame > 20 or index == total_len:
        self.battles.append(current_battle)
        current_battle = []
      prev_frame = current_frame
      current_battle.append(ul)

    new_battles = []
    for battle in self.battles:
      battle_duration = frames_to_irl_seconds(battle[-1]['frame'] - battle[0]['frame'])
      result = {}
      result['start_time'] = battle[0]['time']
      result['end_time'] = battle[-1]['time']
      result['duration'] = battle_duration
      result['units_lost'] = self.units_lost(battle)
      new_battles.append(result)

    return new_battles

  def  units_lost(self, bat):
    sort_battle = sorted(bat, key=operator.itemgetter('pn'))
    units_lost = {}
    for i,units in groupby(sort_battle, key=operator.itemgetter('pn')):
      units_lost[i] = []
      sort_units = sorted(units, key=operator.itemgetter('name'))
      for u, subunits in groupby(sort_units, key=operator.itemgetter('name')):
        units_lost[i].append([len(list(subunits)), self.get_unit_image(u)])
    return units_lost

  def get_unit_image(self, unit_name):
    res = ""
    img_name = self.filter_img_name(unit_name)

    path = f"{ICON_PATH}/units"

    if os.path.isfile(f"{SAVE_ICONS_PATH}/units/{img_name}.jpg"):
      res += f"{path}/{img_name}.jpg"
    else:
      res += unit_name
    return res

  def filter_img_name(self, name):
    img_name = name.lower().replace(" ", "")
    keys = ["reactor", "techlab", "widowmine", "supplydepot", "siegetank"]
    for k in keys:
      if k in img_name:
        img_name = k
        break
    return img_name

def frames_to_irl_seconds(num):
  if num is None:
    num
  else:
    # return (num/16) / 1.4
    return (num/16)

def irl_seconds_to_frames(num):
    # return num * 16 * 1.4
    return num * 16

def getUnits(units = [], time = False,
             finished_before = np.inf, finished_after = 0,
             died_before = np.inf, died_after = 0,
             army = True, workers = True, buildings = True,
             player = None, name = None,replay = None):
  if type(time) != bool:
    died_after = time
    finished_before = time

  died_before = irl_seconds_to_frames(died_before)
  died_after = irl_seconds_to_frames(died_after)
  finished_before = irl_seconds_to_frames(finished_before)
  finished_after = irl_seconds_to_frames(finished_after)

  if player != None:
    if units == []:
      units = player.units
    else:
      units = [unit for unit in units if unit.owner is not None and unit.owner.pid == player.pid]
  elif units == []:
    units = replay.players[0].units + replay.players[1].units
  else:
    units = units

  return [unit for unit in units
    if (unit.finished_at != None and
      unit.finished_at <= finished_before
      and unit.finished_at >= finished_after)

    and (unit.died_at == None
      or unit.died_at >= died_after)

    and (died_before == np.inf or (unit.died_at != None
      and unit.died_at <= died_before))

    and ((unit.is_army and army)
      or (unit.is_worker and workers)
      or (unit.is_building and buildings))

    and (name == None or name in unit.name)]

def getUnitFeatures(features = [], kwargs = {}):
    units = getUnits(**kwargs)

    attributes = [feature for feature in features if feature not in ['player_id','unit']]
    df = pd.DataFrame({feature: [unit.__getattribute__(feature) for unit in units] for feature in attributes},
                      columns=features)

    df.applymap(lambda x:np.nan if x == None else x)

    for col in list(set(df.columns) & set(['started_at','died_at', 'finished_at'])):
        df[col] = df[col].apply(frames_to_irl_seconds).apply(lambda x:int(x)
                                                             if pd.isna(x) == False
                                                             else np.complex('j'))

    special_features = [feature for feature in features if feature in ['player_id','unit']]
    if 'player_id' in special_features:
        try:
            df['player_id'] = [unit.owner.pid for unit in units]
        except:
            df['player_id'] = [unit.owner for unit in units]

    if 'unit' in special_features:
        df['unit'] = units
    return df

# def getXY(iterable):
#   return iterable

#   res = []
#   for obj in iterable:
#     res.append([obj[0], obj[1]])
#   return res

def getLocations(units):
  # return [[unit.location[0], unit.location[1], unit.finished_at, unit.died_at] for unit in units]
  res = {}
  for unit in units:
    if hasattr( unit, 'location' ):
      res[unit.id] = [unit.location[0], unit.location[1]]
  return res

def getUnitType(units = [], name = ''):
  return [unit for unit in units if name in unit.name]

def trackUnitPositions(replay, timeline):
  unit_position_events = [event for event in replay.events if 'UnitPositionsEvent' in event.name]
  res = {}
  for event in unit_position_events:
    new_positions = {}
    for key in event.units.keys():
      new_positions[key.id] = [event.units[key][0], event.units[key][1]]
    update_unit_positions_at_frame(timeline, event.second, new_positions)

def update_unit_positions_at_frame(timeline, second, new_positions):
  state = timeline[second]
  for uid, new_pos in new_positions.items():
    updated = False
    for player_id, workers in state['workers'].items():
      if uid in workers.keys():
        updatePositionSinceTimeTillTheEnd(timeline, second, uid, new_pos, 'workers')
        updated = True
    for player_id, army in state['army'].items():
      if uid in army.keys():
        updatePositionSinceTimeTillTheEnd(timeline, second, uid, new_pos, 'army')
        updated = True
    for player_id, buildings in state['buildings'].items():
      if uid in buildings.keys():
        updatePositionSinceTimeTillTheEnd(timeline, second, uid, new_pos, 'buildings')
        updated = True

def updatePositionSinceTimeTillTheEnd(timeline, second, uid, new_pos, unit_type):
  for t in range(second, list(timeline.keys())[-1], 1):
    for player_id, items in timeline[t][unit_type].items():
      if uid in items.keys():
        items[uid] = new_pos

plot_bounds = {}
def getGameState(
                 all_units = [],
                 replay = None,
                 time = 0,
                 minerals = True,
                 vespene = True,
                 towers = True,
                 workers = True,
                 army = True,
                 buildings = True,
                 ramps = True,
                 kwargs = {}):

    kwargs['time'] = time
    if all_units == []:
      all_units = list(replay.active_units.values())

    p1 = replay.players[0]
    p2 = replay.players[1]

    res = {}
    if minerals:
        mineralfields = getLocations(getUnitType(all_units, name = 'MineralField'))
        res['minerals'] = mineralfields

    if vespene:
        vespenegeyser = getLocations(getUnitType(all_units, name = 'VespeneGeyser'))
        res['vespene'] = vespenegeyser

    if towers:
        xelnagatowers = getLocations(getUnitType(all_units, name = 'XelNagaTower'))
        res['xelnagas'] = xelnagatowers

    if ramps:
        destructibleramp = getLocations(getUnitType(all_units, name = 'Destructible'))
        res['destructable'] = destructibleramp

    if workers:
        p1workers = getLocations(getUnits(units = all_units, player=p1,workers=True, army = False, buildings = False, **kwargs))
        p2workers = getLocations(getUnits(units = all_units, player=p2,workers=True, army = False, buildings = False, **kwargs))

        workers = {}
        workers[p1.pid] = p1workers
        workers[p2.pid] = p2workers
        res['workers'] = workers

    if army:
        p1army = getLocations(getUnits(player=p1,workers=False, army = True, buildings = False, **kwargs))
        p2army = getLocations(getUnits(player=p2,workers=False, army = True, buildings = False, **kwargs))
        army = {}
        army[p1.pid] = p1army
        army[p2.pid] = p2army
        res['army'] = army

    if buildings:
        p1buildings = getLocations(getUnits(player=p1,workers=False, army = False, buildings = True, **kwargs))
        p2buildings = getLocations(getUnits(player=p2,workers=False, army = False, buildings = True, **kwargs))
        buildings = {}
        buildings[p1.pid] = p1buildings
        buildings[p2.pid] = p2buildings
        res['buildings'] = buildings

    mineralfields0 = list(map(lambda x: x[0], mineralfields.values()))
    mineralfields1 = list(map(lambda x: x[1], mineralfields.values()))

    minx = min(mineralfields0) - 20
    maxx = max(mineralfields0) + 20
    miny = min(mineralfields1) - 20
    maxy = max(mineralfields1) + 20

    plot_bounds = {
      'minx': minx,
      'maxx': maxx,
      'miny': miny,
      'maxy': maxy
    }
    return res

def update_born_locations(units, replay):
  unit_born_events  = [event for event in replay.events if 'UnitBornEvent' in event.name and (event.unit.is_worker or event.unit.is_army)]
  for event in unit_born_events:
    born_unit_id = event.unit.id

    found = next((obj for obj in units if obj.id == born_unit_id), None)
    if found is not None:
      # print(found.id, found.name, found.finished_at, found.location, event.location)
      found.location = event.location

def getTimeline(current_game, units = []):
  timeline = {}
  for t in range(0, int(frames_to_irl_seconds(current_game.frames)), 1):
  # for t in range(400, 800, 4):
    timeline[t] = getGameState(all_units = units, time=t, replay=current_game)
  trackUnitPositions(current_game, timeline)
  return timeline


# # path = '/Users/abazov/workspace/unknown/sc2/sc2gg_bot/files/2000 атмосфер РВ (15).SC2Replay'
# # timeline = getTimeline()
# # print(timeline)
# # # path = '/Users/abazov/workspace/unknown/sc2/sc2gg_bot/files/Дропчики теранские.SC2Replay'
# # # path = '/Users/abazov/workspace/unknown/sc2/sc2bot/replays/2020-08-19 - (P)Astrea VS (T)uwuThermal.SC2Replay'
# # path = '/Users/abazov/workspace/unknown/sc2/sc2bot/replays/Давидстайл.SC2Replay'
# # path = '/Users/abazov/workspace/unknown/sc2/sc2bot/replays/ПвТ сам хотел выйти.SC2Replay'
# path = '/Users/abazov/workspace/unknown/sc2/sc2gg_bot/files/Беккетт Индастриз РВ (42).SC2Replay'
# current_game = sc2reader.load_replay(path)
# exporter = Exporter(path)
# exporter.generateHtml()

# # mapInfo(sc2reader.load_replay(path))

# exporter.run()
# # timeline = getTimeline(current_game)
# # trackUnitPositions(current_game, timeline)

# # frame = 10
# # print(f'frame {frame}')
# # print(timeline[frame]['workers'])
# # print(timeline[frame]['army'][1].keys(), timeline[frame]['army'][2].keys())
# # print(timeline[frame]['buildings'])
# # print(timeline)


# # units = current_game.players[0].units + current_game.players[1].units
# # found = next((obj for obj in units if obj.id == 68419585), None)
# # print(found.location)
# # update_born_locations(units, current_game)
# # found = next((obj for obj in units if obj.id == 68419585), None)
# # print(found.location)

# # res = [unit for unit in units if unit.id == 96468993]

# # unit_born  = [event for event in replay.events if 'UnitPositionsEvent' in event.name]

path = '/Users/abazov/workspace/unknown/sc2/sc2gg_bot/files/Беккетт Индастриз РВ (42).SC2Replay'
# current_game = sc2reader.load_replay(path)
exporter = Exporter(path)
exporter.generateHtml()

