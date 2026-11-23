import json
import random
from copy import deepcopy
from typing import Any


def coin_flip(n=1):
    """ทอยเหรียญ n ครั้ง return list ของ 'heads' / 'tails'"""
    return [random.choice(["heads", "tails"]) for _ in range(n)]


class CardDatabase:
    def __init__(self, cards_file='cards.json', decks_file='decks.json'):
        with open(cards_file, 'r', encoding='utf-8') as f:
            cards_data = json.load(f)
            self.cards = {card['id']: card for card in cards_data}

        with open(decks_file, 'r', encoding='utf-8') as f:
            decks_data = json.load(f)
            self.decks = {deck['deck_id']: deck for deck in decks_data}

    def get_card(self, card_id):
        return self.cards.get(card_id)


class PlayerState:
    def __init__(self, name, deck_id, db: CardDatabase):
        self.name = name
        self.points = 0
        self.deck_data = db.decks[deck_id]
        self.energy_type = self.deck_data['energy_type']
        self.db = db

        self.deck = self.deck_data['cards'].copy()
        random.shuffle(self.deck)

        self.hand = []
        self.active_pokemon = None
        self.bench = []  # สูงสุด 3 ตัว
        self.discard_pile = []
        self.energy_zone = 0
        self.max_hand_size = 10
        self.supporter_used_turn = None
        self.attack_damage_bonus_turn = None
        self.attack_damage_bonus = 0

        # --- Retreat ---
        self.retreated_this_turn = False
        self.retreat_cost_reduction = 0  # จาก X Speed

        # --- Ability ---
        self.ability_used_this_turn = {}  # card_id -> bool

        # --- Pending promote ---
        self.pending_promote = False

        # แจกไพ่เริ่มต้น 5 ใบ
        self.draw_cards(5)

    def draw_cards(self, amount):
        drawn = []
        for _ in range(amount):
            if len(self.hand) >= self.max_hand_size:
                break
            if self.deck:
                card_id = self.deck.pop(0)
                self.hand.append(card_id)
                drawn.append(card_id)
        return drawn

    def get_basic_pokemon_in_hand(self):
        basic_pokemons = []
        for card_id in self.hand:
            card_data = self.db.get_card(card_id)
            if card_data and card_data['category'] == 'pokemon' and card_data['stage'] == 'basic':
                basic_pokemons.append(card_id)
        return basic_pokemons

    def _create_in_play_pokemon(self, card_id, card_data, turn_number):
        return {
            "card_id": card_id,
            "name": card_data['name'],
            "type": card_data['type'],
            "max_hp": card_data['hp'],
            "current_hp": card_data['hp'],
            "attached_energy": [],
            "special_conditions": [],
            "turn_played": turn_number,
            "ability_used_this_turn": False,
        }

    def _get_pokemon_slot(self, target_position, target_index=None):
        if target_position == "active":
            if not self.active_pokemon:
                return None, "ไม่มีโปเกมอนในตำแหน่ง Active!"
            return self.active_pokemon, None
        if target_position == "bench":
            if target_index is None or target_index < 0 or target_index >= len(self.bench):
                return None, "ตำแหน่งบนเบนช์ไม่ถูกต้อง!"
            return self.bench[target_index], None
        return None, "ตำแหน่งเป้าหมายไม่ถูกต้อง!"

    def _count_energy_for_cost(self, attached_energy, cost):
        required_by_type: dict[str, int] = {}
        colorless_needed = 0
        for energy in cost:
            if energy == "colorless":
                colorless_needed += 1
            else:
                required_by_type[energy] = required_by_type.get(energy, 0) + 1

        attached_counts = {}
        for energy in attached_energy:
            attached_counts[energy] = attached_counts.get(energy, 0) + 1

        for energy_type, need in required_by_type.items():
            have = attached_counts.get(energy_type, 0)
            if have < need:
                return False

        used_specific = sum(required_by_type.values())
        remaining_energy = len(attached_energy) - used_specific
        return remaining_energy >= colorless_needed

    def _discard_energy_from_pokemon(self, pokemon, energy_type, amount):
        """ทิ้ง energy จากโปเกมอน return จำนวนที่ทิ้งจริง"""
        removed = 0
        for _ in range(amount):
            if energy_type in pokemon["attached_energy"]:
                pokemon["attached_energy"].remove(energy_type)
                removed += 1
            elif pokemon["attached_energy"]:
                # ถ้าไม่มี type ที่ต้องการ ทิ้งอันไหนก็ได้
                pokemon["attached_energy"].pop(0)
                removed += 1
        return removed

    def resolve_inferno_dance(self, target_indexes, selection_count):
        fire_bench_indexes = [
            i for i, bp in enumerate(self.bench)
            if bp.get("type") == "fire"
        ]
        if selection_count <= 0:
            return True, "Inferno Dance ไม่มีพลังงานให้ติด", {
                "energy_attached": 0,
                "attached_targets": [],
                "energy_zone_after": self.energy_zone,
            }

        # Validate and auto-fill targets:
        # - Filter to only valid fire bench indexes
        # - If fewer valid targets than selection_count, repeat cyclically
        # - If no valid targets at all, just skip (attach nothing gracefully)
        valid_targets = [i for i in target_indexes if i in fire_bench_indexes]
        if not valid_targets:
            # No valid fire pokemon targets on bench — just allow graceful skip
            if not fire_bench_indexes:
                return True, "Inferno Dance ไม่มี Fire Pokemon บน Bench ให้ติดพลังงาน", {
                    "energy_zone_before": self.energy_zone,
                    "energy_zone_after": self.energy_zone,
                    "energy_attached": 0,
                    "attached_targets": [],
                }
            # There are fire pokemon but sent wrong indexes — fill from available
            valid_targets = fire_bench_indexes[:]

        # Expand targets to fill selection_count by cycling through valid targets
        if len(valid_targets) < selection_count:
            expanded = []
            for i in range(selection_count):
                expanded.append(valid_targets[i % len(valid_targets)])
            valid_targets = expanded
        else:
            valid_targets = valid_targets[:selection_count]

        attached_targets = []
        energy_before = self.energy_zone
        attached_count = 0
        for idx in valid_targets:
            target = self.bench[idx]
            target["attached_energy"].append("fire")
            attached_count += 1
            attached_targets.append(target["name"])

        return True, "Inferno Dance ติดพลังงานสำเร็จ", {
            "energy_zone_before": energy_before,
            "energy_zone_after": self.energy_zone,
            "energy_attached": attached_count,
            "attached_targets": attached_targets,
        }

    def _discard_active_and_promote(self):
        """KO active pokemon, return (prize_value, ko_name, need_promote)"""
        if not self.active_pokemon:
            return 0, None, False

        knocked_out = self.active_pokemon
        knocked_out_card = self.db.get_card(knocked_out["card_id"])
        prize_value = 1
        if knocked_out_card and knocked_out_card.get("prize_value"):
            prize_value = knocked_out_card["prize_value"]

        self.discard_pile.append({
            "card_id": knocked_out["card_id"],
            "attached_energy": knocked_out["attached_energy"][:]
        })

        if len(self.bench) == 1:
            # มีเหลือตัวเดียว auto promote
            self.active_pokemon = self.bench.pop(0)
            return prize_value, knocked_out["name"], False
        elif len(self.bench) > 1:
            # ให้ผู้เล่นเลือก
            self.active_pokemon = None
            self.pending_promote = True
            return prize_value, knocked_out["name"], True
        else:
            # ไม่มีเหลือ
            self.active_pokemon = None
            return prize_value, knocked_out["name"], False

    def promote_from_bench(self, bench_index):
        """เลือกโปเกมอนจาก bench ขึ้นมา active"""
        if not self.pending_promote:
            return False, "ไม่ต้องเลือก promote"
        if bench_index < 0 or bench_index >= len(self.bench):
            return False, "ตำแหน่งเบนช์ไม่ถูกต้อง!"

        self.active_pokemon = self.bench.pop(bench_index)
        self.pending_promote = False
        return True, f"{self.name} ส่ง {self.active_pokemon['name']} ขึ้นมาเป็น Active!"

    def check_and_mulligan(self):
        mulligan_count = 0
        while not self.get_basic_pokemon_in_hand():
            mulligan_count += 1
            self.deck.extend(self.hand)
            self.hand = []
            random.shuffle(self.deck)
            self.draw_cards(5)
            if mulligan_count > 100:
                break
        return mulligan_count

    def play_basic_to_active(self, card_id, current_turn_number=0):
        if self.active_pokemon is not None:
            return False, "มีโปเกมอน Active อยู่บนฟิลด์แล้ว!"

        if card_id not in self.hand:
            return False, "ไม่มีการ์ดใบนี้บนมือ!"

        card_data = self.db.get_card(card_id)
        if not card_data:
            return False, "ไม่พบข้อมูลการ์ด!"

        if card_data['category'] != 'pokemon' or card_data['stage'] != 'basic':
            return False, "การ์ดใบแรกที่ลงสนามต้องเป็น Basic Pokemon เท่านั้น!"

        self.hand.remove(card_id)
        self.active_pokemon = self._create_in_play_pokemon(card_id, card_data, current_turn_number)

        return True, f"{self.name} ส่ง {card_data['name']} ลงตำแหน่ง Active!"

    def play_to_bench(self, card_id, current_turn_number=0):
        if len(self.bench) >= 3:
            return False, "เบนช์เต็มแล้ว! (วางได้สูงสุด 3 ตัว)"

        if card_id not in self.hand:
            return False, "ไม่มีการ์ดใบนี้บนมือ!"

        card_data = self.db.get_card(card_id)
        if not card_data:
            return False, "ไม่พบข้อมูลการ์ด!"

        if card_data['category'] != 'pokemon' or card_data['stage'] != 'basic':
            return False, "สามารถลงเบนช์ได้เฉพาะ Basic Pokemon เท่านั้น!"

        self.hand.remove(card_id)
        self.bench.append(self._create_in_play_pokemon(card_id, card_data, current_turn_number))

        return True, f"{self.name} วาง {card_data['name']} บนเบนช์"

    def play_basic_to_bench(self, card_id, current_turn_number=0):
        return self.play_to_bench(card_id, current_turn_number)

    def evolve_pokemon(self, evolution_card_id, target_position="active", target_index=0, current_turn_number=0):
        if evolution_card_id not in self.hand:
            return False, "ไม่มีการ์ดวิวัฒนาการใบนี้บนมือ!"

        evolution_card = self.db.get_card(evolution_card_id)
        if not evolution_card:
            return False, "ไม่พบข้อมูลการ์ดวิวัฒนาการ!"

        if evolution_card.get("category") != "pokemon" or evolution_card.get("stage") == "basic":
            return False, "การ์ดที่ใช้วิวัฒนาการต้องเป็น Stage 1 หรือ Stage 2 เท่านั้น"

        target, err = self._get_pokemon_slot(target_position, target_index)
        if err:
            return False, err

        base_card = self.db.get_card(target["card_id"])
        if not base_card:
            return False, "ไม่พบข้อมูลโปเกมอนเป้าหมาย"

        # ไม่สามารถวิวัฒนาการในเทิร์นแรกของผู้เล่นแต่ละคนได้ (เทิร์น 1 และ 2)
        if current_turn_number <= 2 and target.get("turn_played", 0) <= 2:
            return False, "ไม่สามารถวิวัฒนาการโปเกมอนในเทิร์นแรกเริ่มของผู้เล่นได้"

        if target.get("turn_played", 0) >= current_turn_number:
            return False, "ยังวิวัฒนาการไม่ได้: ต้องรออย่างน้อย 1 เทิร์นหลังจากลงสนาม"

        if evolution_card.get("evolves_from") != base_card.get("name"):
            return False, "วิวัฒนาการไม่ถูกต้อง: ร่างเดิมไม่ตรงกับ evolves_from"

        self.hand.remove(evolution_card_id)

        damage_taken = max(target["max_hp"] - target["current_hp"], 0)
        old_name = target["name"]
        target["card_id"] = evolution_card_id
        target["name"] = evolution_card["name"]
        target["type"] = evolution_card["type"]
        target["max_hp"] = evolution_card["hp"]
        target["current_hp"] = max(evolution_card["hp"] - damage_taken, 0)
        target["turn_played"] = current_turn_number
        # วิวัฒนาการลบ special conditions ทั้งหมด
        target["special_conditions"] = []
        target["ability_used_this_turn"] = False

        return True, f"{self.name} วิวัฒนาการ {old_name} -> {evolution_card['name']} สำเร็จ"

    def use_trainer_card(self, card_id, current_turn_number=0, target_position="active",
                         target_index=0, opponent=None, opponent_switch_index=None):
        if card_id not in self.hand:
            return False, "ไม่มีการ์ด Trainer ใบนี้บนมือ!", None

        trainer_card = self.db.get_card(card_id)
        if not trainer_card:
            return False, "ไม่พบข้อมูลการ์ด Trainer", None

        category = trainer_card.get("category")
        if category not in ("item", "supporter"):
            return False, "การ์ดใบนี้ไม่ใช่ Trainer", None

        if category == "supporter" and self.supporter_used_turn == current_turn_number:
            return False, "ใช้ Supporter ได้สูงสุดเทิร์นละ 1 ใบ", None

        effect = trainer_card.get("trainer_effect_calculation")
        extra_data = {}
        supported_trainer_effects = {
            "draw_2_cards",
            "heal_20_from_target",
            "attack_damage_boost_10_this_turn",
            "search_random_basic_pokemon_to_hand",
            "opponent_shuffle_hand_draw_3",
            "opponent_switch_active_to_bench",
            "retreat_cost_reduce_1_this_turn",
        }

        if effect and effect not in supported_trainer_effects:
            return False, f"ยังไม่รองรับเอฟเฟกต์ Trainer: {effect}", None

        # Pre-validation สำหรับบาง effect
        if effect == "opponent_shuffle_hand_draw_3" and not opponent:
            return False, "ระบบผิดพลาด: ไม่พบ opponent", None
        if effect == "opponent_switch_active_to_bench" and opponent:
            if not opponent.active_pokemon or len(opponent.bench) == 0:
                return False, "คู่ต่อสู้ไม่มี bench pokemon ให้สลับ", None
            if len(opponent.bench) > 1 and opponent_switch_index is None:
                return False, "ต้องระบุ bench index ของฝั่งตรงข้ามสำหรับการสลับจาก Sabrina", None

        self.hand.remove(card_id)
        self.discard_pile.append({"card_id": card_id})

        if category == "supporter":
            self.supporter_used_turn = current_turn_number

        if effect == "draw_2_cards":
            drawn = self.draw_cards(2)
            extra_data["drawn"] = drawn

        elif effect == "heal_20_from_target":
            target, err = self._get_pokemon_slot(target_position, target_index)
            if err:
                return True, f"ใช้ {trainer_card['name']} แล้ว แต่{err}", extra_data
            old_hp = target["current_hp"]
            target["current_hp"] = min(target["max_hp"], target["current_hp"] + 20)
            extra_data["healed"] = target["current_hp"] - old_hp

        elif effect == "attack_damage_boost_10_this_turn":
            self.attack_damage_bonus_turn = current_turn_number
            self.attack_damage_bonus = 10

        elif effect == "search_random_basic_pokemon_to_hand":
            # Poké Ball: สุ่มหา Basic Pokemon จาก deck
            basics_in_deck = []
            for i, cid in enumerate(self.deck):
                cd = self.db.get_card(cid)
                if cd and cd['category'] == 'pokemon' and cd['stage'] == 'basic':
                    basics_in_deck.append(i)
            if basics_in_deck:
                idx = random.choice(basics_in_deck)
                found_card_id = self.deck.pop(idx)
                self.hand.append(found_card_id)
                found_card = self.db.get_card(found_card_id)
                extra_data["found"] = found_card["name"] if found_card else found_card_id
            else:
                extra_data["found"] = None

        elif effect == "opponent_shuffle_hand_draw_3" and opponent:
            # Red Card
            opponent.deck.extend(opponent.hand)
            opponent.hand = []
            random.shuffle(opponent.deck)
            opponent.draw_cards(3)
            extra_data["opponent_new_hand_count"] = len(opponent.hand)

        elif effect == "opponent_switch_active_to_bench" and opponent:
            # Sabrina: คู่ต่อสู้ต้องสลับ active -> bench
            if opponent.bench:
                opponent.bench.append(opponent.active_pokemon)
                # หลัง append active เก่าเข้า bench ตำแหน่งสุดท้ายห้ามเลือกกลับมาเป็น active ทันที
                last_idx = len(opponent.bench) - 1
                if opponent_switch_index is None:
                    new_active_idx = 0
                else:
                    new_active_idx = opponent_switch_index
                if new_active_idx < 0 or new_active_idx >= last_idx:
                    return False, "bench index ที่เลือกสำหรับ Sabrina ไม่ถูกต้อง", None
                opponent.active_pokemon = opponent.bench.pop(new_active_idx)
                extra_data["new_active"] = opponent.active_pokemon["name"]

        elif effect == "retreat_cost_reduce_1_this_turn":
            # X Speed
            self.retreat_cost_reduction += 1
            extra_data["retreat_reduction"] = self.retreat_cost_reduction

        return True, f"{self.name} ใช้การ์ด {trainer_card['name']} สำเร็จ", extra_data

    def use_ability(self, pokemon_position="active", pokemon_index=0, current_turn_number=0):
        """ใช้ Ability ของโปเกมอน"""
        target, err = self._get_pokemon_slot(pokemon_position, pokemon_index)
        if err:
            return False, err, None

        card_data = self.db.get_card(target["card_id"])
        if not card_data or not card_data.get("ability"):
            return False, "โปเกมอนตัวนี้ไม่มี Ability!", None

        ability = card_data["ability"]

        if ability.get("once_per_turn") and target.get("ability_used_this_turn"):
            return False, f"ใช้ {ability['name']} ได้แค่ 1 ครั้ง/เทิร์น", None

        # Implement specific abilities
        ability_name = ability["name"]
        extra_data = {"ability_name": ability_name}

        if ability_name == "Psy Shadow":
            # ติด Psychic Energy ให้ Active โดยไม่หักจาก Energy Zone
            if not self.active_pokemon:
                return False, "ไม่มี Active Pokemon ให้ติดพลังงาน!", None
            self.active_pokemon["attached_energy"].append("psychic")
            extra_data["attached_to"] = self.active_pokemon["name"]
            extra_data["energy_type"] = "psychic"
            extra_data["energy_zone_after"] = self.energy_zone
        else:
            return False, f"Ability '{ability_name}' ยังไม่รองรับ", None

        target["ability_used_this_turn"] = True
        return True, f"{self.name} ใช้ Ability {ability_name}!", extra_data

    def retreat(self, bench_index, current_turn_number=0):
        """ถอย Active Pokemon กลับ bench แล้วส่ง bench ตัวที่เลือกขึ้นมา active"""
        if self.retreated_this_turn:
            return False, "ถอยได้แค่ 1 ครั้ง/เทิร์น!", None

        if not self.active_pokemon:
            return False, "ไม่มี Active Pokemon!", None

        if bench_index < 0 or bench_index >= len(self.bench):
            return False, "ตำแหน่ง bench ไม่ถูกต้อง!", None

        # เช็ค special conditions
        if "paralysis" in self.active_pokemon.get("special_conditions", []):
            return False, "โปเกมอนเป็นอัมพาต ถอยไม่ได้!", None
        if "sleep" in self.active_pokemon.get("special_conditions", []):
            return False, "โปเกมอนหลับอยู่ ถอยไม่ได้!", None

        card_data = self.db.get_card(self.active_pokemon["card_id"])
        if not card_data:
            return False, "ไม่พบข้อมูลการ์ด!", None

        retreat_cost = len(card_data.get("retreat_cost", []))
        effective_cost = max(0, retreat_cost - self.retreat_cost_reduction)

        if len(self.active_pokemon["attached_energy"]) < effective_cost:
            return False, f"พลังงานไม่พอ! ต้องใช้ {effective_cost} (ค่าเดิม {retreat_cost}, ลด {self.retreat_cost_reduction})", None

        # Discard energy ตาม retreat cost
        for _ in range(effective_cost):
            if self.active_pokemon["attached_energy"]:
                self.active_pokemon["attached_energy"].pop(0)

        old_active = self.active_pokemon
        old_name = old_active["name"]
        self.active_pokemon = self.bench.pop(bench_index)
        new_name = self.active_pokemon["name"]
        self.bench.append(old_active)

        self.retreated_this_turn = True

        return True, f"{old_name} ถอย! {new_name} ขึ้นมาเป็น Active!", {
            "old_active": old_name,
            "new_active": new_name,
            "energy_discarded": effective_cost
        }

    def execute_attack(self, opponent, attack_name, current_turn_number=0,
                       bench_target_index=None, self_bench_target_index=None, fire_attach_targets=None):
        if not self.active_pokemon:
            return False, "โจมตีไม่ได้: ไม่มี Active Pokemon", None
        if not opponent.active_pokemon:
            return False, "โจมตีไม่ได้: ฝั่งตรงข้ามไม่มี Active Pokemon", None

        # เช็ค special conditions
        conditions = self.active_pokemon.get("special_conditions", [])
        if "sleep" in conditions:
            return False, "โปเกมอนหลับอยู่ ตีไม่ได้!", None
        if "paralysis" in conditions:
            return False, "โปเกมอนเป็นอัมพาต ตีไม่ได้!", None

        # Confusion check
        if "confusion" in conditions:
            flip = coin_flip(1)
            if flip[0] == "tails":
                # ตีตัวเอง 30 damage
                self.active_pokemon["current_hp"] -= 30
                confused_result = {
                    "confused": True,
                    "coin_result": "tails",
                    "self_damage": 30
                }
                ko = False
                if self.active_pokemon["current_hp"] <= 0:
                    ko = True
                    prize, ko_name, need_promote = self._discard_active_and_promote()
                    opponent.points += prize
                    confused_result["self_ko"] = True
                return True, f"{self.active_pokemon['name'] if not ko else 'โปเกมอน'} สับสนและตีตัวเอง!", confused_result

        attacker_card = self.db.get_card(self.active_pokemon["card_id"])
        defender_card = self.db.get_card(opponent.active_pokemon["card_id"])
        if not attacker_card or not defender_card:
            return False, "ข้อมูลการ์ดไม่ครบสำหรับการโจมตี", None

        selected_attack = None
        for attack in attacker_card.get("attacks", []):
            if attack.get("name") == attack_name:
                selected_attack = attack
                break

        if not selected_attack:
            return False, "ไม่พบท่าที่ต้องการโจมตี", None

        if not self._count_energy_for_cost(self.active_pokemon["attached_energy"], selected_attack.get("cost", [])):
            return False, "พลังงานไม่พอสำหรับใช้ท่านี้", None

        damage = selected_attack.get("damage", 0)
        targets_opponent_active = True
        effect_calc = selected_attack.get("effect_calculation")
        supported_attack_effects = {
            None,
            "coin_flip_3_attach_fire_energy_from_zone",
            "damage_multiplied_by_benched_count",
            "damage_multiplied_by_heads_50",
            "damage_self_bench_30",
            "damage_to_opponent_pokemon_30",
            "discard_1_energy_from_self",
            "discard_2_energy_from_self",
            "discard_2_fire_energy_from_self",
            "discard_2_psychic_energy_from_self",
        }
        if effect_calc not in supported_attack_effects:
            return False, f"ยังไม่รองรับเอฟเฟกต์ท่าโจมตี: {effect_calc}", None

        extra_data = {
            "attack_name": selected_attack.get("name"),
            "coin_results": [],
        }

        # --- Apply attack effects ---
        if effect_calc == "damage_multiplied_by_benched_count":
            # Pikachu ex (Circle Circuit): ดาเมจ 30 ต่อ Pokemon 1 ตัวบน Bench ฝั่งตัวเอง
            bench_count = len(self.bench)
            damage = 30 * bench_count
            extra_data["bench_count"] = bench_count

        elif effect_calc == "damage_multiplied_by_heads_50":
            # Zapdos ex: ทอย 4 เหรียญ × 50/หัว
            flips = coin_flip(4)
            heads = flips.count("heads")
            damage = 50 * heads
            extra_data["coin_results"] = flips
            extra_data["heads_count"] = heads

        elif effect_calc == "coin_flip_3_attach_fire_energy_from_zone":
            # Moltres ex: ทอย 3 เหรียญ แล้วค่อยให้ผู้เล่นเลือกเป้าหมายทีละหัว
            flips = coin_flip(3)
            heads = flips.count("heads")
            extra_data["coin_results"] = flips
            extra_data["heads_count"] = heads
            extra_data["energy_zone_before"] = self.energy_zone

            fire_bench_indexes = [
                i for i, bp in enumerate(self.bench)
                if bp.get("type") == "fire"
            ]
            if not fire_bench_indexes:
                extra_data["attach_blocked_reason"] = "ไม่มี Fire Pokemon บน Bench"
                heads = 0

            selection_count = heads
            extra_data["selection_count"] = selection_count
            extra_data["available_bench_indexes"] = fire_bench_indexes

            if selection_count > 0:
                extra_data["pending_choice"] = True
                extra_data["energy_attached"] = 0
                extra_data["attached_targets"] = []
                extra_data["energy_zone_after"] = self.energy_zone
                return True, f"{self.name} ใช้ {selected_attack.get('name')} รอเลือกเป้าหมาย {selection_count} ครั้ง", extra_data

            extra_data["pending_choice"] = False
            extra_data["energy_attached"] = 0
            extra_data["attached_targets"] = []
            extra_data["energy_zone_after"] = self.energy_zone
            # damage ยังเป็น 0 (ท่านี้ไม่ทำ damage)

        # --- Post-attack effects ---
        if effect_calc == "discard_2_fire_energy_from_self":
            self._discard_energy_from_pokemon(self.active_pokemon, "fire", 2)
            extra_data["discarded_energy"] = {"type": "fire", "amount": 2}

        elif effect_calc == "discard_1_energy_from_self":
            self._discard_energy_from_pokemon(self.active_pokemon, self.energy_type, 1)
            extra_data["discarded_energy"] = {"type": self.energy_type, "amount": 1}

        elif effect_calc == "discard_2_energy_from_self":
            self._discard_energy_from_pokemon(self.active_pokemon, self.energy_type, 2)
            extra_data["discarded_energy"] = {"type": self.energy_type, "amount": 2}

        elif effect_calc == "discard_2_psychic_energy_from_self":
            self._discard_energy_from_pokemon(self.active_pokemon, "psychic", 2)
            extra_data["discarded_energy"] = {"type": "psychic", "amount": 2}

        elif effect_calc == "damage_self_bench_30":
            # Zapdos: ตี bench ตัวเอง 30
            if self.bench:
                idx = self_bench_target_index if self_bench_target_index is not None else 0
                if 0 <= idx < len(self.bench):
                    self.bench[idx]["current_hp"] -= 30
                    extra_data["self_bench_damage"] = {
                        "target": self.bench[idx]["name"],
                        "damage": 30
                    }
                    # เช็ค KO bench ตัวเอง
                    if self.bench[idx]["current_hp"] <= 0:
                        ko_bench = self.bench.pop(idx)
                        self.discard_pile.append({
                            "card_id": ko_bench["card_id"],
                            "attached_energy": ko_bench["attached_energy"][:]
                        })
                        extra_data["self_bench_ko"] = ko_bench["name"]

        elif effect_calc == "damage_to_opponent_pokemon_30":
            # Zebstrika: เลือกยิงโปเกมอนฝั่งตรงข้าม 1 ตัว 30
            if bench_target_index is not None:
                targets_opponent_active = False
                damage = 0
                if 0 <= bench_target_index < len(opponent.bench):
                    opponent.bench[bench_target_index]["current_hp"] -= 30
                    extra_data["bench_damage"] = {
                        "target": opponent.bench[bench_target_index]["name"],
                        "damage": 30
                    }
                    if opponent.bench[bench_target_index]["current_hp"] <= 0:
                        ko_bench = opponent.bench.pop(bench_target_index)
                        opponent.discard_pile.append({
                            "card_id": ko_bench["card_id"],
                            "attached_energy": ko_bench["attached_energy"][:]
                        })
                        bench_ko_card = self.db.get_card(ko_bench["card_id"])
                        prize_val = 1
                        if bench_ko_card and bench_ko_card.get("prize_value"):
                            prize_val = bench_ko_card["prize_value"]
                        self.points += prize_val
                        extra_data["bench_ko"] = ko_bench["name"]
                        extra_data["bench_ko_prize"] = prize_val
            elif opponent.active_pokemon:
                targets_opponent_active = True
                damage = 30
                extra_data["snipe_damage"] = 30

        # Giovanni bonus มีผลเฉพาะตอนโจมตี Active ของคู่ต่อสู้
        if targets_opponent_active and self.attack_damage_bonus_turn == current_turn_number:
            damage += self.attack_damage_bonus

        # Weakness/Resistance มีผลเฉพาะตอนโจมตี Active ของคู่ต่อสู้
        weakness = defender_card.get("weakness")
        if targets_opponent_active and weakness and weakness.get("type") == attacker_card.get("type"):
            damage += weakness.get("multiplier", 20)
            extra_data["weakness_bonus"] = weakness.get("multiplier", 20)

        resistance = defender_card.get("resistance")
        if targets_opponent_active and resistance and resistance.get("type") == attacker_card.get("type"):
            damage = max(0, damage - resistance.get("value", 20))
            extra_data["resistance_reduction"] = resistance.get("value", 20)

        # Apply damage to opponent active
        if targets_opponent_active and damage > 0:
            opponent.active_pokemon["current_hp"] -= damage

        # เช็ค KO opponent active
        ko = False
        ko_name = None
        prize_gained = 0
        need_promote = False
        if opponent.active_pokemon and opponent.active_pokemon["current_hp"] <= 0:
            ko = True
            prize_gained, ko_name, need_promote = opponent._discard_active_and_promote()
            self.points += prize_gained

        extra_data["damage"] = damage
        extra_data["ko"] = ko
        extra_data["ko_target"] = ko_name
        extra_data["prize_gained"] = prize_gained
        extra_data["need_promote"] = need_promote

        return True, f"{self.name} ใช้ {selected_attack.get('name')} สร้างดาเมจ {damage}", extra_data

    def apply_special_condition(self, condition, pokemon=None):
        """ใส่ condition ให้โปเกมอน"""
        if pokemon is None:
            pokemon = self.active_pokemon
        if not pokemon:
            return
        conditions = pokemon.get("special_conditions", [])
        # Paralysis/Sleep/Confusion แทนที่กัน
        mutually_exclusive = ["paralysis", "sleep", "confusion"]
        if condition in mutually_exclusive:
            for c in mutually_exclusive:
                if c in conditions:
                    conditions.remove(c)
        if condition not in conditions:
            conditions.append(condition)
        pokemon["special_conditions"] = conditions

    def check_pokemon_conditions(self):
        """เช็คสถานะ ณ ท้ายเทิร์น (Pokemon Check Phase)"""
        events = []
        if not self.active_pokemon:
            return events

        conditions = self.active_pokemon.get("special_conditions", [])

        # Poison: -10 HP
        if "poison" in conditions:
            self.active_pokemon["current_hp"] -= 10
            events.append({"type": "poison", "damage": 10})

        # Burn: ทอยเหรียญ
        if "burn" in conditions:
            flip = coin_flip(1)
            if flip[0] == "tails":
                self.active_pokemon["current_hp"] -= 20
                events.append({"type": "burn", "coin": "tails", "damage": 20})
            else:
                events.append({"type": "burn", "coin": "heads", "damage": 0})

        # Sleep: ทอยเหรียญเพื่อตื่น
        if "sleep" in conditions:
            flip = coin_flip(1)
            if flip[0] == "heads":
                conditions.remove("sleep")
                events.append({"type": "sleep", "coin": "heads", "woke_up": True})
            else:
                events.append({"type": "sleep", "coin": "tails", "woke_up": False})

        # Paralysis: หายหลัง 1 เทิร์น
        if "paralysis" in conditions:
            conditions.remove("paralysis")
            events.append({"type": "paralysis", "removed": True})

        self.active_pokemon["special_conditions"] = conditions
        return events

    def attach_energy(self, target_position, target_index=None):
        if self.energy_zone <= 0:
            return False, "ไม่มีพลังงานในโซน!"

        target, err = self._get_pokemon_slot(target_position, target_index)
        if err:
            return False, err

        target["attached_energy"].append(self.energy_type)
        self.energy_zone -= 1

        return True, f"ติดพลังงาน {self.energy_type} ให้ {target['name']}"

    def reset_turn_flags(self):
        """Reset flags ที่ต้อง reset ทุกเทิร์น"""
        self.retreated_this_turn = False
        self.retreat_cost_reduction = 0
        self.attack_damage_bonus_turn = None
        self.attack_damage_bonus = 0
        # Reset ability usage for all pokemon
        if self.active_pokemon:
            self.active_pokemon["ability_used_this_turn"] = False
        for bp in self.bench:
            bp["ability_used_this_turn"] = False

    def get_card_details_for_hand(self):
        """ดึงข้อมูลการ์ดในมือแบบ detail สำหรับ Frontend"""
        details = []
        for card_id in self.hand:
            card_data = self.db.get_card(card_id)
            if card_data:
                details.append({
                    "id": card_id,
                    "name": card_data.get("name"),
                    "category": card_data.get("category"),
                    "type": card_data.get("type"),
                    "stage": card_data.get("stage"),
                    "hp": card_data.get("hp"),
                    "evolves_from": card_data.get("evolves_from"),
                    "attacks": card_data.get("attacks", []),
                    "retreat_cost": card_data.get("retreat_cost", []),
                    "trainer_effect": card_data.get("trainer_effect"),
                    "trainer_effect_calculation": card_data.get("trainer_effect_calculation"),
                })
        return details

    def get_active_attacks(self):
        """ดึงข้อมูลท่าโจมตีของ Active Pokemon"""
        if not self.active_pokemon:
            return []
        card_data = self.db.get_card(self.active_pokemon["card_id"])
        if not card_data:
            return []
        attacks = card_data.get("attacks", [])
        result = []
        for atk in attacks:
            can_use = self._count_energy_for_cost(
                self.active_pokemon["attached_energy"],
                atk.get("cost", [])
            )
            result.append({
                "name": atk["name"],
                "cost": atk.get("cost", []),
                "damage": atk.get("damage", 0),
                "effect": atk.get("effect"),
                "effect_calculation": atk.get("effect_calculation"),
                "can_use": can_use,
            })
        return result

    def get_active_ability(self):
        """ดึงข้อมูล Ability ของ Active Pokemon"""
        if not self.active_pokemon:
            return None
        card_data = self.db.get_card(self.active_pokemon["card_id"])
        if not card_data or not card_data.get("ability"):
            return None
        ability = card_data["ability"]
        return {
            "name": ability["name"],
            "effect": ability["effect"],
            "can_use": not self.active_pokemon.get("ability_used_this_turn", False),
        }

    def get_bench_abilities(self):
        """ดึงข้อมูล Ability ของโปเกมอนบนเบนช์"""
        abilities = []
        for idx, pokemon in enumerate(self.bench):
            card_data = self.db.get_card(pokemon["card_id"])
            if not card_data or not card_data.get("ability"):
                continue
            ability = card_data["ability"]
            abilities.append({
                "index": idx,
                "name": ability["name"],
                "effect": ability["effect"],
                "can_use": not pokemon.get("ability_used_this_turn", False),
            })
        return abilities

    def get_state_json(self):
        # Enrich active/bench snapshots with static retreat cost from card database.
        active_with_cost = self.active_pokemon
        if self.active_pokemon:
            active_with_cost = dict(self.active_pokemon)
            cd = self.db.get_card(self.active_pokemon.get("card_id")) or {}
            active_with_cost["retreat_cost"] = cd.get("retreat_cost", [])

        bench_with_cost = []
        for bp in self.bench:
            bpc = dict(bp)
            cd = self.db.get_card(bp.get("card_id")) or {}
            bpc["retreat_cost"] = cd.get("retreat_cost", [])
            bench_with_cost.append(bpc)

        return {
            "name": self.name,
            "points": self.points,
            "energy_type": self.energy_type,
            "energy_zone": self.energy_zone,
            "deck_count": len(self.deck),
            "hand": self.hand,
            "hand_details": self.get_card_details_for_hand(),
            "active_pokemon": active_with_cost,
            "active_attacks": self.get_active_attacks(),
            "active_ability": self.get_active_ability(),
            "bench_abilities": self.get_bench_abilities(),
            "bench": bench_with_cost,
            "discard_pile": self.discard_pile,
            "supporter_used_turn": self.supporter_used_turn,
            "retreated_this_turn": self.retreated_this_turn,
            "retreat_cost_reduction": self.retreat_cost_reduction,
            "pending_promote": self.pending_promote,
        }


class GameState:
    def __init__(self, player1_name, p1_deck_id, player2_name, p2_deck_id, db: CardDatabase):
        self.db = db
        self.p1 = PlayerState(player1_name, p1_deck_id, db)
        self.p2 = PlayerState(player2_name, p2_deck_id, db)

        self.p1.check_and_mulligan()
        self.p2.check_and_mulligan()

        self.setup_phase = True
        self.pending_initial_active = {self.p1.name, self.p2.name}

        self.turn_number = 1
        self.current_turn = random.choice([self.p1.name, self.p2.name])
        self.first_player_name = self.current_turn
        self.winner = None
        self.game_over = False
        self.phase = "setup"
        self.pending_effect = None
        
        self.latest_ai_thought = ""

        self.last_played_card = None
        self.last_played_card_id = 0

        # Action log
        self.action_log: list[dict[str, Any]] = []
        self.event_log: list[dict[str, Any]] = []

    def _log(self, message, data=None):
        entry = {"turn": self.turn_number, "message": message}
        entry["phase"] = self.phase
        if data:
            entry["data"] = data
        self.action_log.append(entry)
        # Keep last 30 entries
        if len(self.action_log) > 30:
            self.action_log = self.action_log[-30:]  # type: ignore

    def set_last_played(self, player_name, card_id):
        self.last_played_card = {"player": player_name, "card_id": card_id}
        self.last_played_card_id += 1

    def _compact_state(self):
        def compact_player(player):
            return {
                "points": player.points,
                "deck": len(player.deck),
                "hand": len(player.hand),
                "energy_zone": player.energy_zone,
                "active": None if not player.active_pokemon else {
                    "id": player.active_pokemon.get("card_id"),
                    "hp": player.active_pokemon.get("current_hp"),
                    "energy": len(player.active_pokemon.get("attached_energy", [])),
                },
                "bench": [
                    {
                        "id": b.get("card_id"),
                        "hp": b.get("current_hp"),
                        "energy": len(b.get("attached_energy", [])),
                    }
                    for b in player.bench
                ],
                "pending_promote": player.pending_promote,
            }

        return {
            "turn": self.turn_number,
            "current_turn": self.current_turn,
            "phase": self.phase,
            "setup_phase": self.setup_phase,
            "pending_initial_active": sorted(self.pending_initial_active),
            "p1": compact_player(self.p1),
            "p2": compact_player(self.p2),
            "game_over": self.game_over,
            "winner": self.winner,
            "last_played_card": self.last_played_card,
            "last_played_card_id": self.last_played_card_id,
        }

    def _build_state_diff(self, before, after):
        diff = {}
        keys = set(before.keys()) | set(after.keys())
        for key in keys:
            if before.get(key) != after.get(key):
                diff[key] = {"before": before.get(key), "after": after.get(key)}
        return diff

    def _record_event(self, action, actor, success, message, before_state, after_state, extra=None):
        event = {
            "turn": self.turn_number,
            "phase": self.phase,
            "action": action,
            "actor": actor,
            "success": success,
            "message": message,
            "before": before_state,
            "after": after_state,
            "diff": self._build_state_diff(before_state, after_state),
        }
        if extra is not None:
            event["extra"] = extra
        self.event_log.append(event)
        if len(self.event_log) > 200:
            self.event_log = self.event_log[-200:]

    def get_player_by_name(self, player_name):
        if self.p1.name == player_name:
            return self.p1
        if self.p2.name == player_name:
            return self.p2
        return None

    def select_initial_active(self, player_name, card_id):
        if not self.setup_phase:
            return False, "เกมเริ่มแล้ว ไม่อยู่ในช่วงเลือก Active เริ่มเกม"

        if player_name not in self.pending_initial_active:
            return False, "ผู้เล่นนี้เลือก Active เริ่มเกมไปแล้ว"

        player = self.get_player_by_name(player_name)
        if not player:
            return False, "ไม่พบผู้เล่นนี้ในเกม"

        success, message = player.play_basic_to_active(card_id, self.turn_number)
        if not success:
            return False, message

        self.pending_initial_active.remove(player_name)
        if not self.pending_initial_active:
            self.setup_phase = False
            self.phase = "draw"
            # เริ่มเทิร์นแรก: จั่ว 1 ใบ แต่ยังไม่เติมพลังงานให้ผู้เล่นเริ่มก่อน
            self._begin_turn(self.get_current_player(), grant_energy=False)
            return True, f"{message} ตั้งค่าเริ่มเกมครบแล้ว เริ่มเทิร์น 1 ของ {self.current_turn}"

        return True, f"{message} เหลือผู้เล่นที่ต้องเลือก Active: {', '.join(sorted(self.pending_initial_active))}"

    def _is_first_player_first_turn(self):
        return (
            not self.setup_phase
            and self.turn_number == 1
            and self.current_turn == self.first_player_name
        )

    def _begin_turn(self, player, grant_energy=True):
        self.phase = "draw"
        drawn = player.draw_cards(1)

        # Deck-out timing: ถ้าต้องจั่วตอนเริ่มเทิร์นแต่ deck ว่างและจั่วไม่ได้ => แพ้ทันที
        if len(drawn) == 0 and len(player.deck) == 0:
            opponent = self.p2 if player == self.p1 else self.p1
            self.winner = opponent.name
            self.game_over = True
            self.phase = "ended"
            self._log(f"{player.name} จั่วตอนเริ่มเทิร์นไม่สำเร็จ (deck หมด) => {opponent.name} ชนะ")
            return

        if grant_energy:
            player.energy_zone = 1
        player.reset_turn_flags()

        data = {
            "player": player.name,
            "drawn": drawn,
            "hand_count": len(player.hand),
            "deck_count": len(player.deck),
            "energy_zone": player.energy_zone,
        }
        self._log(f"เริ่มเทิร์น {player.name} (เทิร์นที่ {self.turn_number})", data)
        self.phase = "main"

    def switch_turn(self):
        if self.setup_phase:
            return "ยังสลับเทิร์นไม่ได้: ทั้งสองฝั่งต้องเลือก Active ก่อนเริ่มเทิร์น 1"

        self.phase = "check"
        # Pokemon Check ก่อนจบเทิร์น
        current_player = self.get_current_player()
        condition_events = current_player.check_pokemon_conditions()
        for evt in condition_events:
            self._log(f"Pokemon Check: {evt['type']}", evt)

        # เช็ค KO จาก conditions
        if current_player.active_pokemon and current_player.active_pokemon["current_hp"] <= 0:
            opponent = self.get_opponent()
            prize, ko_name, need_promote = current_player._discard_active_and_promote()
            opponent.points += prize
            self._log(f"{ko_name} ถูก KO จาก condition!")

        # สลับเทิร์น
        if self.current_turn == self.p1.name:
            self.current_turn = self.p2.name
        else:
            self.current_turn = self.p1.name
        self.turn_number += 1

        # เริ่มเทิร์นใหม่: จั่ว 1 + เติมพลังงาน 1
        new_player = self.get_current_player()
        self._begin_turn(new_player, grant_energy=True)

        msg = f"เริ่มเทิร์น {self.current_turn} (เทิร์นที่ {self.turn_number})"
        return msg

    def get_current_player(self):
        if self.current_turn == self.p1.name:
            return self.p1
        else:
            return self.p2

    def get_opponent(self):
        if self.current_turn == self.p1.name:
            return self.p2
        else:
            return self.p1

    def check_winner(self):
        if self.setup_phase:
            return False, "ยังอยู่ในช่วงเริ่มเกม"

        if self.game_over:
            return True, f"เกมจบแล้ว: {self.winner} เป็นผู้ชนะ"

        if self.p1.points >= 3:
            self.winner = self.p1.name
            self.game_over = True
            self.phase = "ended"
            self._log(f"{self.p1.name} ชนะ! (ได้ 3 คะแนน)")
            return True, f"{self.p1.name} ชนะ! (ได้ 3 คะแนน)"
        elif self.p2.points >= 3:
            self.winner = self.p2.name
            self.game_over = True
            self.phase = "ended"
            self._log(f"{self.p2.name} ชนะ! (ได้ 3 คะแนน)")
            return True, f"{self.p2.name} ชนะ! (ได้ 3 คะแนน)"

        p1_has = self.p1.active_pokemon is not None or len(self.p1.bench) > 0
        p2_has = self.p2.active_pokemon is not None or len(self.p2.bench) > 0

        if not p1_has:
            self.winner = self.p2.name
            self.game_over = True
            self.phase = "ended"
            return True, f"{self.p2.name} ชนะ! (คู่ต่อสู้ไม่มีโปเกมอนเหลือ)"
        elif not p2_has:
            self.winner = self.p1.name
            self.game_over = True
            self.phase = "ended"
            return True, f"{self.p1.name} ชนะ! (คู่ต่อสู้ไม่มีโปเกมอนเหลือ)"

        return False, "เกมยังดำเนินต่อไป"

    def _validate_turn_action(self, player_name):
        if self.game_over:
            return False, "เกมจบแล้ว ไม่สามารถทำแอคชันเพิ่มได้", None, None

        if self.pending_effect is not None:
            return False, "มีเอฟเฟกต์ค้างอยู่ ต้องเลือกเป้าหมายให้เสร็จก่อน", None, None

        if self.phase != "main":
            return False, f"ตอนนี้ยังไม่ใช่ Main Phase (phase ปัจจุบัน: {self.phase})", None, None

        player = self.get_player_by_name(player_name)
        if not player:
            return False, "ไม่พบผู้เล่นนี้ในเกม", None, None

        if self.current_turn != player_name:
            return False, "ยังไม่ใช่เทิร์นของคุณ!", None, None

        opponent = self.get_opponent() if self.get_current_player() == player else self.get_current_player()
        return True, "ok", player, opponent

    def action_play_active(self, player_name, card_id):
        before_state = self._compact_state()
        if self.setup_phase:
            success, message = self.select_initial_active(player_name, card_id)
            self.check_winner()
            self._record_event("play_active", player_name, success, message, before_state, self._compact_state())
            return success, message, None

        valid, message, player, _ = self._validate_turn_action(player_name)
        if not valid:
            return False, message, None

        success, message = player.play_basic_to_active(card_id, self.turn_number)
        if success:
            self._log(message)
        self.check_winner()
        self._record_event("play_active", player_name, success, message, before_state, self._compact_state())
        return success, message, None

    def action_play_bench(self, player_name, card_id):
        before_state = self._compact_state()
        if self.setup_phase:
            player = self.get_player_by_name(player_name)
            if not player:
                self._record_event("play_bench", player_name, False, "ไม่พบผู้เล่นนี้ในเกม", before_state, self._compact_state())
                return False, "ไม่พบผู้เล่นนี้ในเกม", None

            success, message = player.play_to_bench(card_id, self.turn_number)
            if success:
                self._log(message)
            self._record_event("play_bench", player_name, success, message, before_state, self._compact_state())
            return success, message, None

        valid, message, player, _ = self._validate_turn_action(player_name)
        if not valid:
            return False, message, None

        success, message = player.play_to_bench(card_id, self.turn_number)
        if success:
            self._log(message)
        self.check_winner()
        self._record_event("play_bench", player_name, success, message, before_state, self._compact_state())
        return success, message, None

    def action_evolve(self, player_name, evolution_card_id, target_position="active", target_index=0):
        before_state = self._compact_state()
        if self.setup_phase:
            self._record_event("evolve", player_name, False, "ยังวิวัฒนาการไม่ได้: ต้องเลือก Active เริ่มเกมให้ครบก่อน", before_state, self._compact_state())
            return False, "ยังวิวัฒนาการไม่ได้: ต้องเลือก Active เริ่มเกมให้ครบก่อน", None

        valid, message, player, _ = self._validate_turn_action(player_name)
        if not valid:
            return False, message, None

        success, message = player.evolve_pokemon(
            evolution_card_id,
            target_position=target_position,
            target_index=target_index,
            current_turn_number=self.turn_number,
        )
        if success:
            self._log(message)
            self.set_last_played(player_name, evolution_card_id)
        self.check_winner()
        self._record_event("evolve", player_name, success, message, before_state, self._compact_state())
        return success, message, None

    def action_use_trainer(self, player_name, card_id, target_position="active", target_index=0, opponent_switch_index=None):
        before_state = self._compact_state()
        if self.setup_phase:
            self._record_event("use_trainer", player_name, False, "ยังใช้ Trainer ไม่ได้: ต้องเลือก Active เริ่มเกมให้ครบก่อน", before_state, self._compact_state())
            return False, "ยังใช้ Trainer ไม่ได้: ต้องเลือก Active เริ่มเกมให้ครบก่อน", None

        valid, message, player, opponent = self._validate_turn_action(player_name)
        if not valid:
            return False, message, None

        success, message, extra_data = player.use_trainer_card(
            card_id,
            current_turn_number=self.turn_number,
            target_position=target_position,
            target_index=target_index,
            opponent=opponent,
            opponent_switch_index=opponent_switch_index,
        )
        if success:
            self._log(message, extra_data)
            self.set_last_played(player_name, card_id)
        self.check_winner()
        self._record_event("use_trainer", player_name, success, message, before_state, self._compact_state(), extra_data)
        return success, message, extra_data

    def action_attack(self, player_name, attack_name, bench_target_index=None,
                      self_bench_target_index=None, fire_attach_targets=None):
        before_state = self._compact_state()
        if self.setup_phase:
            self._record_event("attack", player_name, False, "ยังโจมตีไม่ได้: ต้องเลือก Active เริ่มเกมให้ครบก่อน", before_state, self._compact_state())
            return False, "ยังโจมตีไม่ได้: ต้องเลือก Active เริ่มเกมให้ครบก่อน", None

        valid, message, player, opponent = self._validate_turn_action(player_name)
        if not valid:
            return False, message, None

        if self._is_first_player_first_turn():
            return False, "ผู้เล่นเริ่มก่อนห้ามโจมตีในเทิร์นแรก", None

        success, message, attack_result = player.execute_attack(
            opponent,
            attack_name,
            current_turn_number=self.turn_number,
            bench_target_index=bench_target_index,
            self_bench_target_index=self_bench_target_index,
            fire_attach_targets=fire_attach_targets,
        )
        if success:
            self._log(message, attack_result)
        is_game_over, win_msg = self.check_winner()

        # Inferno Dance: รอผู้เล่นเลือกเป้าหมายหลังทอยเหรียญ
        if success and attack_result and attack_result.get("pending_choice"):
            self.pending_effect = {
                "type": "inferno_dance",
                "player_name": player_name,
                "selection_count": attack_result.get("selection_count", 0),
                "available_bench_indexes": attack_result.get("available_bench_indexes", []),
                "coin_results": attack_result.get("coin_results", []),
                "heads_count": attack_result.get("heads_count", 0),
            }
            self._record_event("attack", player_name, success, message, before_state, self._compact_state(), attack_result)
            return success, message, attack_result
        
        # ถ้าโจมตีสำเร็จและเกมยังไม่จบ ให้จบเทิร์นอัตโนมัติ
        if success and not is_game_over:
            # เช็คว่ามี pending promote ไหม ถ้ามีต้องรอเลือกก่อน
            current = self.get_current_player()
            opponent = self.get_opponent()
            if not current.pending_promote and not opponent.pending_promote:
                turn_msg = self.switch_turn()
                message += f" | {turn_msg}"

        self._record_event("attack", player_name, success, message, before_state, self._compact_state(), attack_result)
        return success, message, attack_result

    def action_resolve_pending_effect(self, player_name, target_indexes):
        before_state = self._compact_state()
        if not self.pending_effect:
            self._record_event("resolve_effect", player_name, False, "ไม่มีเอฟเฟกต์ค้างให้เลือก", before_state, self._compact_state())
            return False, "ไม่มีเอฟเฟกต์ค้างให้เลือก", None

        if self.pending_effect.get("type") != "inferno_dance":
            self._record_event("resolve_effect", player_name, False, "ยังไม่รองรับเอฟเฟกต์ค้างชนิดนี้", before_state, self._compact_state())
            return False, "ยังไม่รองรับเอฟเฟกต์ค้างชนิดนี้", None

        if self.pending_effect.get("player_name") != player_name:
            self._record_event("resolve_effect", player_name, False, "ไม่ใช่ผู้เล่นที่ต้องเลือกเอฟเฟกต์นี้", before_state, self._compact_state())
            return False, "ไม่ใช่ผู้เล่นที่ต้องเลือกเอฟเฟกต์นี้", None

        player = self.get_player_by_name(player_name)
        if not player:
            self._record_event("resolve_effect", player_name, False, "ไม่พบผู้เล่นนี้ในเกม", before_state, self._compact_state())
            return False, "ไม่พบผู้เล่นนี้ในเกม", None

        success, message, extra = player.resolve_inferno_dance(
            target_indexes,
            self.pending_effect.get("selection_count", 0),
        )
        if not success:
            self._record_event("resolve_effect", player_name, False, message, before_state, self._compact_state())
            return False, message, None

        coin_results = self.pending_effect.get("coin_results", [])
        heads_count = self.pending_effect.get("heads_count", 0)
        self.pending_effect = None

        result = {
            "ability_like_effect": "Inferno Dance",
            "coin_results": coin_results,
            "heads_count": heads_count,
            **(extra or {}),
        }
        self._log(message, result)
        is_game_over, _ = self.check_winner()
        if not is_game_over:
            current = self.get_current_player()
            opponent = self.get_opponent()
            if not current.pending_promote and not opponent.pending_promote:
                turn_msg = self.switch_turn()
                message = f"{message} | {turn_msg}"

        self._record_event("resolve_effect", player_name, True, message, before_state, self._compact_state(), result)
        return True, message, result

    def action_attach_energy(self, player_name, target_position, target_index=0):
        before_state = self._compact_state()
        if self.setup_phase:
            self._record_event("attach_energy", player_name, False, "ยังติดพลังงานไม่ได้", before_state, self._compact_state())
            return False, "ยังติดพลังงานไม่ได้", None

        valid, message, player, _ = self._validate_turn_action(player_name)
        if not valid:
            self._record_event("attach_energy", player_name, False, message, before_state, self._compact_state())
            return False, message, None

        if self._is_first_player_first_turn():
            msg = "ผู้เล่นเริ่มก่อนห้ามติดพลังงานในเทิร์นแรก"
            self._record_event("attach_energy", player_name, False, msg, before_state, self._compact_state())
            return False, msg, None

        success, message = player.attach_energy(target_position, target_index)
        if success:
            self._log(message, {"target_position": target_position, "target_index": target_index})
        self.check_winner()
        self._record_event("attach_energy", player_name, success, message, before_state, self._compact_state())
        return success, message, None

    def action_retreat(self, player_name, bench_index):
        before_state = self._compact_state()
        if self.setup_phase:
            self._record_event("retreat", player_name, False, "ยังถอยไม่ได้: ต้องเลือก Active เริ่มเกมให้ครบก่อน", before_state, self._compact_state())
            return False, "ยังถอยไม่ได้: ต้องเลือก Active เริ่มเกมให้ครบก่อน", None

        valid, message, player, _ = self._validate_turn_action(player_name)
        if not valid:
            return False, message, None

        success, message, extra = player.retreat(bench_index, self.turn_number)
        if success:
            self._log(message, extra)
        self.check_winner()
        self._record_event("retreat", player_name, success, message, before_state, self._compact_state(), extra)
        return success, message, extra

    def action_use_ability(self, player_name, pokemon_position="active", pokemon_index=0):
        before_state = self._compact_state()
        if self.setup_phase:
            self._record_event("use_ability", player_name, False, "ยังใช้ Ability ไม่ได้", before_state, self._compact_state())
            return False, "ยังใช้ Ability ไม่ได้", None

        valid, message, player, _ = self._validate_turn_action(player_name)
        if not valid:
            return False, message, None

        success, message, extra = player.use_ability(
            pokemon_position, pokemon_index, self.turn_number
        )
        if success:
            self._log(message, extra)
        self.check_winner()
        self._record_event("use_ability", player_name, success, message, before_state, self._compact_state(), extra)
        return success, message, extra

    def action_promote(self, player_name, bench_index):
        """เลือก bench pokemon ขึ้นมาเป็น active หลัง KO"""
        before_state = self._compact_state()
        player = self.get_player_by_name(player_name)
        if not player:
            self._record_event("promote", player_name, False, "ไม่พบผู้เล่น", before_state, self._compact_state())
            return False, "ไม่พบผู้เล่น", None

        success, message = player.promote_from_bench(bench_index)
        if success:
            self._log(message)
        is_game_over, _ = self.check_winner()

        if success and not is_game_over:
            current = self.get_current_player()
            opponent = self.get_opponent()
            if not current.pending_promote and not opponent.pending_promote:
                turn_msg = self.switch_turn()
                message = f"{message} | {turn_msg}"

        self._record_event("promote", player_name, success, message, before_state, self._compact_state())
        return success, message, None

    def action_concede(self, player_name):
        """ยอมแพ้"""
        before_state = self._compact_state()
        if self.game_over:
            self._record_event("concede", player_name, False, "เกมจบแล้ว", before_state, self._compact_state())
            return False, "เกมจบแล้ว", None

        player = self.get_player_by_name(player_name)
        if not player:
            return False, "ไม่พบผู้เล่น", None

        opponent = self.p2 if player == self.p1 else self.p1
        self.winner = opponent.name
        self.game_over = True
        self.phase = "ended"
        msg = f"{player.name} ยอมแพ้! {opponent.name} เป็นผู้ชนะ!"
        self._log(msg)
        self._record_event("concede", player_name, True, msg, before_state, self._compact_state())
        return True, msg, None

    def action_end_turn(self):
        before_state = self._compact_state()
        if self.setup_phase:
            self._record_event("end_turn", self.current_turn, False, "ยังจบเทิร์นไม่ได้: ทั้งสองฝั่งต้องเลือก Active ก่อนเริ่มเทิร์น 1", before_state, self._compact_state())
            return False, "ยังจบเทิร์นไม่ได้: ทั้งสองฝั่งต้องเลือก Active ก่อนเริ่มเทิร์น 1", None
        if self.game_over:
            self._record_event("end_turn", self.current_turn, False, "เกมจบแล้ว ไม่สามารถจบเทิร์นต่อได้", before_state, self._compact_state())
            return False, "เกมจบแล้ว ไม่สามารถจบเทิร์นต่อได้", None

        # เช็คว่ามี pending promote ไหม
        current = self.get_current_player()
        opponent = self.get_opponent()
        if current.pending_promote or opponent.pending_promote:
            self._record_event("end_turn", self.current_turn, False, "ต้องเลือก Pokemon ขึ้นมา Active ก่อนจบเทิร์น", before_state, self._compact_state())
            return False, "ต้องเลือก Pokemon ขึ้นมา Active ก่อนจบเทิร์น", None

        message = self.switch_turn()
        self.check_winner()
        self._record_event("end_turn", self.current_turn, True, message, before_state, self._compact_state())
        return True, message, None

    def get_full_state(self):
        return {
            "turn_number": self.turn_number,
            "current_turn": self.current_turn,
            "first_player": self.first_player_name,
            "phase": self.phase,
            "setup_phase": self.setup_phase,
            "pending_effect": self.pending_effect,
            "pending_initial_active": sorted(self.pending_initial_active),
            "game_over": self.game_over,
            "winner": self.winner,
            "latest_ai_thought": self.latest_ai_thought,
            "player_1": self.p1.get_state_json(),
            "player_2": self.p2.get_state_json(),
            "action_log": self.action_log[-10:],
        }