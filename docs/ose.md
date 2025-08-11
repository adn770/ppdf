# OSE Core Rules

## Dice Notation
Dice rolls are described with the notation **XdY**:
* **X** is the number of dice to be rolled.
* **Y** is the number of sides on each die.
* For example, **3d6** means "roll three 6-sided dice and add the results together".
* A modifier may be added to the roll, for example **2d4+2** means "roll two 4-sided dice, add the results, and then add 2".

## Key Terms
* **Referee (Ref):** The player who designs the game world, presents challenges, and arbitrates the rules.
* **Players:** The other participants, each controlling a single character.
* **Player Character (PC):** A character controlled by a player.
* **Non-Player Character (NPC):** Any character controlled by the Referee.
* **Party:** The group of PCs who go on adventures together.
* **Adventure:** A single quest or mission, such as exploring a dungeon.
* **Campaign:** A series of adventures, often with a recurring cast of PCs.
* **Ability Scores:** The six scores that define a character's basic capabilities: Strength (STR), Intelligence (INT), Wisdom (WIS), Dexterity (DEX), Constitution (CON), and Charisma (CHA).
* **Class:** A character's profession or archetype (e.g., Fighter, Cleric, Magic-User).
* **Level:** A measure of a character's experience and power. Characters start at 1st level.
* **Experience Points (XP):** Awarded by the Referee for overcoming challenges. Accumulating XP allows a character to advance in level.
* **Alignment:** A character's moral and ethical stance, chosen from Law, Neutrality, or Chaos.
* **Hit Points (hp):** A measure of a character's ability to survive damage. A character's current hp total is tracked separately from their maximum. Damage reduces current hp.
* **Hit Dice (HD):** The type of die used to determine a character's (or monster's) maximum hit points.
* **Armor Class (AC):** A measure of a character's ability to avoid being hit in combat. The OSE SRD uses two systems: Descending AC (lower is better, unarmored is 9) and Ascending AC (higher is better, unarmored is 10). This document presents Descending AC first, with the Ascending AC value in brackets `[ ]`. For example: **AC 7 [12]**.
* **Attack Roll:** A roll to determine if an attack hits. In OSE, this is often resolved using a table or the THAC0 system.
* **THAC0:** An acronym for "To Hit Armor Class 0". This is the number a character needs to roll on a d20 to hit an opponent with AC 0. The number needed to hit other AC values is found by subtracting the target's AC from the THAC0.
* **Saving Throw (Save):** A roll to avoid or reduce the effect of a special attack, spell, or hazard. There are five categories: Death (or poison), Wands, Paralysis (or petrify), Breath Attacks, Spells (or rods/staves).
* **Movement Rate (MV):** The speed at which a character can move. This is listed as a base rate for exploration and an encounter rate (in parentheses) for combat. For example: **120' (40')**.

# Character Creation

Follow these steps to create a player character:

1.  **Roll Ability Scores:** Roll 3d6 for each of the six ability scores, in order: Strength, Intelligence, Wisdom, Dexterity, Constitution, and Charisma.
2.  **Choose a Class:** Select a character class based on your ability scores. Some classes have minimum score requirements.
3.  **Note Ability Modifiers:** Based on your ability scores, note the associated modifiers on your character sheet.
4.  **Roll Hit Points:** Roll the Hit Die type specified by your class and add your Constitution modifier. This is your starting maximum hp.
5.  **Note Saving Throws and Class Abilities:** Record the saving throw values and special abilities for your class. If you are a spellcaster, note your starting spells.
6.  **Buy Equipment:** Your character starts with 3d6 × 10 gold pieces (gp). Spend this on weapons, armor, and adventuring gear.
7.  **Note Armor Class:** Calculate your character's AC based on the armor and shield they are using, modified by their Dexterity score.
8.  **Note THAC0:** Your character's THAC0 is determined by their class and level.
9.  **Choose Alignment:** Decide if your character is Lawful, Neutral, or Chaotic.
10. **Name Your Character:** Give your character a name and any other finishing details. You are now ready to play!

## Ability Scores

| Score | STR Modifier | INT Modifier | WIS Modifier | DEX Modifier | CON Modifier | CHA Modifier |
|:-----:|:------------:|:------------:|:------------:|:------------:|:------------:|:------------:|
| 3     | -3           | Illiterate   | -3           | -3           | -3           | -2           |
| 4–5   | -2           | Illiterate   | -2           | -2           | -2           | -1           |
| 6–8   | -1           | Basic        | -1           | -1           | -1           | -1           |
| 9–12  | None         | Literate     | None         | None         | None         | None         |
| 13–15 | +1           | Literate     | +1           | +1           | +1           | +1           |
| 16–17 | +2           | Literate     | +2           | +2           | +2           | +1           |
| 18    | +3           | Literate     | +3           | +3           | +3           | +2           |

* **Strength (STR):** Affects melee attacks and damage.
* **Intelligence (INT):** Affects literacy and number of languages known. Required for Magic-Users.
* **Wisdom (WIS):** Affects saving throws against magic. Required for Clerics.
* **Dexterity (DEX):** Affects Armor Class, missile attacks, and initiative.
* **Constitution (CON):** Affects hit points.
* **Charisma (CHA):** Affects reactions from NPCs and the number of retainers you can hire.

# Character Classes

## Cleric
**Requirements:** Minimum WIS 9  
**Hit Dice:** 1d6  
**Armor:** Any, including shields  
**Weapons:** Any blunt weapons (club, mace, sling, staff, war hammer)  
**Prime Requisite:** WIS

Clerics are holy warriors who pledge their service to a divine power. They are trained in combat and can call upon their deity for magical aid.

| Level | XP      | HD   | THAC0 | D | W | P | B | S | Spells (1st, 2nd, 3rd) |
|:-----:|:-------:|:----:|:-----:|:-:|:-:|:-:|:-:|:-:|:----------------------:|
| 1     | 0       | 1d6  | 19[+0]| 11| 12| 14| 16| 15| 1, -, -                |
| 2     | 1,500   | 2d6  | 19[+0]| 11| 12| 14| 16| 15| 2, -, -                |
| 3     | 3,000   | 3d6  | 19[+0]| 11| 12| 14| 16| 15| 2, 1, -                |
| 4     | 6,000   | 4d6  | 19[+0]| 11| 12| 14| 16| 15| 2, 2, -                |
| 5     | 12,000  | 5d6  | 17[+2]| 9 | 10| 12| 14| 12| 2, 2, 1                |

**Class Abilities:**
* **Divine Magic:** Can cast divine spells. Must carry a holy symbol.
* **Turning Undead:** Can invoke divine power to repel or destroy undead monsters.

## Fighter
**Requirements:** Minimum STR 9  
**Hit Dice:** 1d8  
**Armor:** Any, including shields  
**Weapons:** Any  
**Prime Requisite:** STR

Fighters are specialists in combat and masters of all weapons. Their role in an adventuring party is to fight monsters and defend their comrades.

| Level | XP      | HD   | THAC0 | D | W | P | B | S |
|:-----:|:-------:|:----:|:-----:|:-:|:-:|:-:|:-:|:-:|
| 1     | 0       | 1d8  | 19[+0]| 12| 13| 14| 15| 16|
| 2     | 2,000   | 2d8  | 19[+0]| 12| 13| 14| 15| 16|
| 3     | 4,000   | 3d8  | 19[+0]| 12| 13| 14| 15| 16|
| 4     | 8,000   | 4d8  | 17[+2]| 10| 11| 12| 13| 14|
| 5     | 16,000  | 5d8  | 17[+2]| 10| 11| 12| 13| 14|

## Magic-User
**Requirements:** Minimum INT 9  
**Hit Dice:** 1d4  
**Armor:** None  
**Weapons:** Dagger, staff  
**Prime Requisite:** INT

Magic-Users are students of the arcane arts, able to manipulate reality through powerful spells. They are physically frail, relying on their magic for survival.

| Level | XP      | HD   | THAC0 | D | W | P | B | S | Spells (1st, 2nd, 3rd) |
|:-----:|:-------:|:----:|:-----:|:-:|:-:|:-:|:-:|:-:|:----------------------:|
| 1     | 0       | 1d4  | 19[+0]| 13| 14| 13| 16| 15| 1, -, -                |
| 2     | 2,500   | 2d4  | 19[+0]| 13| 14| 13| 16| 15| 2, -, -                |
| 3     | 5,000   | 3d4  | 19[+0]| 13| 14| 13| 16| 15| 2, 1, -                |
| 4     | 10,000  | 4d4  | 19[+0]| 13| 14| 13| 16| 15| 2, 2, -                |
| 5     | 20,000  | 5d4  | 17[+2]| 11| 12| 11| 14| 12| 2, 2, 1                |

**Class Abilities:**
* **Arcane Magic:** Cast spells from spell books. Starts with one spell (plus *Read Magic*).
* **Magical Research:** Can research new spells and create magic items at higher levels.

## Thief
**Requirements:** Minimum DEX 9  
**Hit Dice:** 1d4  
**Armor:** Leather, no shields  
**Weapons:** Any  
**Prime Requisite:** DEX

Thieves are specialists in stealth, lock-picking, and disarming traps. They are cunning and adaptable, though not always trustworthy.

| Level | XP      | HD   | THAC0 | D | W | P | B | S |
|:-----:|:-------:|:----:|:-----:|:-:|:-:|:-:|:-:|:-:|
| 1     | 0       | 1d4  | 19[+0]| 13| 14| 13| 16| 15|
| 2     | 1,200   | 2d4  | 19[+0]| 13| 14| 13| 16| 15|
| 3     | 2,400   | 3d4  | 19[+0]| 13| 14| 13| 16| 15|
| 4     | 4,800   | 4d4  | 17[+2]| 12| 13| 12| 15| 14|
| 5     | 9,600   | 5d4  | 17[+2]| 12| 13| 12| 15| 14|

**Class Abilities:**
* **Back-Stab:** +4 to hit and double damage when attacking an unaware opponent from behind.
* **Thief Skills:** A set of unique skills for stealth and infiltration (see table below).

**Thief Skills (d% or X-in-6 chance of success)**

| Skill               | Lvl 1 | Lvl 2 | Lvl 3 | Lvl 4 | Lvl 5 |
|:--------------------|:-----:|:-----:|:-----:|:-----:|:-----:|
| Climb Sheer Surfaces| 87%   | 88%   | 89%   | 90%   | 91%   |
| Find/Remove Traps   | 10%   | 15%   | 20%   | 25%   | 30%   |
| Hear Noise          | 1-in-6| 1-in-6| 2-in-6| 2-in-6| 2-in-6|
| Hide in Shadows     | 10%   | 15%   | 20%   | 25%   | 30%   |
| Move Silently       | 20%   | 25%   | 30%   | 35%   | 40%   |
| Open Locks          | 15%   | 20%   | 25%   | 30%   | 35%   |
| Pick Pockets        | 20%   | 25%   | 30%   | 35%   | 40%   |

# Equipment

## Weapons

| Weapon         | Damage | Cost (gp) | Qualities                                     |
|:---------------|:------:|:---------:|:----------------------------------------------|
| Battle axe     | 1d8    | 7         | Melee, Two-handed                               |
| Club           | 1d4    | 3         | Blunt, Melee                                  |
| Dagger         | 1d4    | 3         | Melee, Missile (5-10' / 11-20' / 21-30')        |
| Hand axe       | 1d6    | 4         | Melee, Missile (5-10' / 11-20' / 21-30')        |
| Long bow       | 1d8    | 40        | Missile (5-70' / 71-140' / 141-210'), Two-handed |
| Mace           | 1d6    | 5         | Blunt, Melee                                  |
| Short bow      | 1d6    | 25        | Missile (5-50' / 51-100' / 101-150'), Two-handed |
| Short sword    | 1d6    | 7         | Melee                                         |
| Sling          | 1d4    | 2         | Blunt, Missile (5-40' / 41-80' / 81-160')       |
| Spear          | 1d6    | 3         | Brace, Melee, Missile (5-20' / 21-40' / 41-60') |
| Staff          | 1d4    | 2         | Blunt, Melee, Two-handed                        |
| Sword          | 1d8    | 10        | Melee                                         |
| Two-handed sword| 1d10   | 15        | Melee, Slow, Two-handed                       |
| War hammer     | 1d6    | 5         | Blunt, Melee                                  |

## Armor

| Armor          | AC Bonus | Cost (gp) |
|:---------------|:--------:|:---------:|
| Leather armor  | +2 [AC 7]| 20        |
| Chainmail      | +4 [AC 5]| 40        |
| Plate mail     | +6 [AC 3]| 60        |
| Shield         | +1       | 10        |

## Adventuring Gear

| Item                 | Cost (gp) |
|:---------------------|:---------:|
| Backpack             | 2         |
| Crowbar              | 2         |
| Flask of oil         | 1         |
| Grappling hook       | 1         |
| Hammer (small)       | 1         |
| Holy water (vial)    | 25        |
| Iron spikes (12)     | 1         |
| Lantern              | 5         |
| Mirror (hand-sized)  | 10        |
| Pole (10' wooden)    | 1         |
| Rations (iron, 1 wk) | 15        |
| Rations (std, 1 wk)  | 5         |
| Rope (50' hemp)      | 1         |
| Sack (large)         | 2 sp      |
| Thieves' tools       | 25        |
| Tinderbox            | 3         |
| Torches (6)          | 1         |
| Waterskin            | 1         |

# Combat

## Combat Sequence Per Round (10 seconds)

1.  **Declare Spells and Retreats:** Players intending to cast a spell or retreat from melee must declare it.
2.  **Initiative:** Each side rolls 1d6. The side with the higher roll acts first.
3.  **Winning Side Acts:**
    a. **Morale Check:** The Referee may check NPC morale.
    b. **Movement:** Characters move up to their encounter movement rate.
    c. **Missile Attacks:** Characters with missile weapons may fire.
    d. **Spell Casting:** Spells that were declared are cast.
    e. **Melee Attacks:** Characters in melee may attack.
4.  **Losing Side Acts:** The side that lost initiative follows the same steps.

## Attacking

1.  **Roll 1d20:** The attacker rolls 1d20.
2.  **Apply Modifiers:** The roll is modified by the character's STR (for melee) or DEX (for missile), and any situational modifiers.
3.  **Determine Hit:** The modified roll is compared to the target's AC. Using THAC0, the attack hits if `d20 roll >= THAC0 - Target AC`.
4.  **Roll Damage:** If the attack hits, the attacker rolls the appropriate damage die for their weapon, adding any STR modifiers for melee attacks.

## Saving Throws
When a character is subjected to a special attack or effect, they may be allowed a saving throw to avoid or reduce the outcome.
1.  **Roll 1d20:** The player rolls 1d20.
2.  **Determine Success:** If the roll is greater than or equal to the character's saving throw value for that category, the save is successful.

# A Sample of Monsters

## Goblin
Small, grotesque humanoids with a foul temper and a love of dark places. They fear the sun.
**AC** 7 [12], **HD** 1-1 (3hp), **Att** 1 × weapon (1d6), **THAC0** 19 [+0], **MV** 60’ (20’), **SV** D14 W15 P16 B17 S18 (NH), **ML** 7, **AL** Chaotic, **XP** 5, **NA** 2d4 (6d10), **TT** R

* **Hate sunlight:** -1 to attack rolls in bright light.
* **Infravision:** 90'.

## Ogre
Large, ugly, and brutish humanoids who live by raiding and theft. They are greedy and quick to anger.
**AC** 5 [14], **HD** 4+1 (19hp), **Att** 1 × club (1d10), **THAC0** 15 [+4], **MV** 90’ (30’), **SV** D10 W11 P12 B13 S14 (4), **ML** 10, **AL** Chaotic, **XP** 125, **NA** 1d6 (2d6), **TT** C

* **Large sack:** Ogres often carry a sack with their belongings (and sometimes unfortunate captives).

## Skeleton
Animated bones of the dead, mindlessly following the commands of their creator.
**AC** 8 [11], **HD** 1 (4hp), **Att** 1 × weapon (1d6), **THAC0** 19 [+0], **MV** 60’ (20’), **SV** D12 W13 P14 B15 S16 (1), **ML** 12, **AL** Neutral, **XP** 10, **NA** 3d4 (3d10), **TT** None

* **Undead:** Immune to effects that affect living creatures (e.g., poison, sleep, charm).
* **Edged weapon immunity:** Only take half damage from edged or piercing weapons.
