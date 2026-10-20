/* Loki Dive — rare-answer trivia bank.
 * Mechanics inspired by the daily game krillion.io, rebuilt original here:
 * every prompt takes one answer; the rarer the answer, the deeper you sink.
 * Answers are stored flat and lowercase; the engine folds diacritics and
 * punctuation, so "piña colada" matches either spelling.
 */
"use strict";
(function () {
  const tiers = [
    { key: "plankton", name: "Plankton", points: 10, note: "the answer everyone gives first" },
    { key: "clever", name: "Too Clever", points: 15, note: "valid, but still crowded" },
    { key: "schooler", name: "Schooler", points: 30, note: "a smaller school gave this" },
    { key: "rare", name: "Rare", points: 60, note: "uncommon and accepted" },
    { key: "deep", name: "Deep Cut", points: 85, note: "very few players found this" },
    { key: "zillion", name: "One in a Zillion", points: 100, note: "trench territory" }
  ];
  /* [answer, tierIndex] pairs. Tier 5 is the rarest. */
  const prompts = [
    {
      q: "Name a bird",
      rules: "Any bird species counts.",
      a: [
        ["parrot", 0], ["eagle", 0], ["owl", 0], ["penguin", 0], ["sparrow", 0], ["duck", 0],
        ["chicken", 1], ["pigeon", 1], ["seagull", 1], ["goose", 1], ["turkey", 1], ["hawk", 1],
        ["crow", 2], ["swan", 2], ["ostrich", 2], ["hummingbird", 2], ["peacock", 2], ["flamingo", 2],
        ["pelican", 3], ["kestrel", 3], ["woodpecker", 3], ["finch", 3], ["starling", 3], ["swallow", 3],
        ["nightingale", 4], ["puffin", 4], ["albatross", 4], ["kingfisher", 4], ["egret", 4], ["kiwi", 4],
        ["cassowary", 5], ["shoebill", 5], ["secretary bird", 5], ["hoatzin", 5], ["potoo", 5]
      ]
    },
    {
      q: "Name a fruit",
      rules: "If your greengrocer sells it as fruit, it counts.",
      a: [
        ["apple", 0], ["banana", 0], ["orange", 0], ["grape", 0], ["watermelon", 0], ["strawberry", 0], ["cherry", 0],
        ["mango", 1], ["pineapple", 1], ["peach", 1], ["pear", 1], ["kiwi", 1], ["blackberry", 1],
        ["plum", 2], ["pomegranate", 2], ["apricot", 2], ["raspberry", 2], ["grapefruit", 2],
        ["lychee", 3], ["passionfruit", 3], ["dragon fruit", 3], ["nectarine", 3],
        ["persimmon", 4], ["guava", 4], ["starfruit", 4], ["fig", 4], ["loquat", 4], ["mulberry", 4],
        ["feijoa", 5], ["ackee", 5], ["salak", 5], ["jabuticaba", 5], ["ugli fruit", 5]
      ]
    },
    {
      q: "Name an animal that lives in the ocean",
      rules: "It has to actually live there — no beach tourists.",
      a: [
        ["shark", 0], ["dolphin", 0], ["whale", 0], ["octopus", 0], ["jellyfish", 0], ["crab", 0],
        ["turtle", 1], ["seahorse", 1], ["lobster", 1], ["squid", 1], ["eel", 1], ["stingray", 1],
        ["seal", 2], ["starfish", 2], ["penguin", 2], ["anglerfish", 2], ["walrus", 2],
        ["narwhal", 3], ["manatee", 3], ["sea otter", 3], ["manta ray", 3],
        ["cuttlefish", 4], ["mantis shrimp", 4], ["sea cucumber", 4], ["moray eel", 4], ["lamprey", 4],
        ["siphonophore", 5], ["dumbo octopus", 5], ["vampire squid", 5], ["giant isopod", 5], ["gulper eel", 5]
      ]
    },
    {
      q: "Name a US state",
      rules: "All fifty count. Obscurity is your friend.",
      a: [
        ["california", 0], ["texas", 0], ["new york", 0], ["florida", 0],
        ["ohio", 1], ["michigan", 1], ["arizona", 1], ["illinois", 1], ["washington", 1],
        ["oregon", 2], ["colorado", 2], ["alabama", 2], ["kentucky", 2],
        ["nebraska", 3], ["idaho", 3], ["missouri", 3], ["wisconsin", 3], ["vermont", 3],
        ["wyoming", 4], ["mississippi", 4], ["delaware", 4], ["maine", 4], ["west virginia", 4],
        ["arkansas", 5], ["iowa", 5], ["new hampshire", 5], ["rhode island", 5]
      ]
    },
    {
      q: "Name a Harry Potter character",
      rules: "Anyone named in the books or films counts.",
      a: [
        ["harry potter", 0], ["hermione granger", 0], ["ron weasley", 0], ["dumbledore", 0], ["voldemort", 0], ["snape", 0],
        ["hagrid", 1], ["draco malfoy", 1], ["sirius black", 1], ["mad eye moody", 1], ["dobby", 1],
        ["neville longbottom", 2], ["luna lovegood", 2], ["bellatrix lestrange", 2], ["remus lupin", 2], ["fred weasley", 2], ["tonks", 2],
        ["cedric diggory", 3], ["fleur delacour", 3], ["viktor krum", 3], ["rita skeeter", 3], ["moaning myrtle", 3],
        ["horace slughorn", 4], ["filius flitwick", 4], ["aberforth", 4], ["angelina johnson", 4], ["madam pomfrey", 4],
        ["madam pince", 5], ["dedalus diggle", 5], ["cuthbert binns", 5], ["auntie muriel", 5], ["madam puddifoot", 5]
      ]
    },
    {
      q: "Name a language people speak",
      rules: "Spoken languages — programming languages don't count here.",
      a: [
        ["english", 0], ["spanish", 0], ["french", 0], ["chinese", 0],
        ["japanese", 1], ["german", 1], ["arabic", 1], ["hindi", 1], ["portuguese", 1], ["russian", 1],
        ["italian", 2], ["korean", 2], ["polish", 2], ["dutch", 2], ["finnish", 2],
        ["swahili", 3], ["vietnamese", 3], ["thai", 3], ["greek", 3],
        ["tagalog", 4], ["yoruba", 4], ["farsi", 4], ["hausa", 4], ["igbo", 4],
        ["quechua", 5], ["inuktitut", 5], ["guarani", 5], ["chamorro", 5], ["anishinaabe", 5]
      ]
    },
    {
      q: "Name a vegetable",
      rules: "Kitchens decide. We are not relitigating the tomato — it counts.",
      a: [
        ["carrot", 0], ["potato", 0], ["broccoli", 0], ["onion", 0], ["tomato", 0],
        ["spinach", 1], ["garlic", 1], ["cucumber", 1], ["pumpkin", 1],
        ["cauliflower", 2], ["kale", 2], ["asparagus", 2], ["beetroot", 2],
        ["parsnip", 3], ["turnip", 3], ["radish", 3], ["celery", 3],
        ["swede", 4], ["celeriac", 4], ["chard", 4], ["watercress", 4], ["fennel", 4],
        ["salsify", 5], ["scorzonera", 5], ["yacon", 5], ["samphire", 5], ["oca", 5]
      ]
    },
    {
      q: "Name a Greek god or goddess",
      rules: "Mythology counts, including the quiet ones.",
      a: [
        ["zeus", 0], ["poseidon", 0], ["hades", 0], ["athena", 0],
        ["apollo", 1], ["ares", 1], ["hermes", 1], ["aphrodite", 1],
        ["artemis", 2], ["hera", 2], ["demeter", 2], ["dionysus", 2], ["persephone", 2],
        ["hestia", 3], ["eris", 3], ["nike", 3], ["iris", 3],
        ["hypnos", 4], ["thanatos", 4], ["helios", 4], ["selene", 4], ["nyx", 4],
        ["hemera", 5], ["aether", 5], ["metis", 5], ["caerus", 5], ["antheia", 5]
      ]
    },
    {
      q: "Name a metal",
      rules: "Elements and everyday alloys both count.",
      a: [
        ["iron", 0], ["gold", 0], ["silver", 0], ["copper", 0],
        ["aluminium", 1], ["mercury", 1], ["platinum", 1], ["zinc", 1],
        ["nickel", 2], ["tin", 2], ["brass", 2], ["tungsten", 2], ["lead", 2],
        ["magnesium", 3], ["manganese", 3], ["palladium", 3], ["bismuth", 3],
        ["cobalt", 4], ["zirconium", 4], ["antimony", 4], ["molybdenum", 4], ["iridium", 4],
        ["osmium", 5], ["rhenium", 5], ["promethium", 5], ["holmium", 5], ["dysprosium", 5]
      ]
    },
    {
      q: "Name a car brand",
      rules: "Any maker that sold cars to the public.",
      a: [
        ["toyota", 0], ["ford", 0], ["tesla", 0], ["bmw", 0], ["mercedes benz", 0],
        ["honda", 1], ["audi", 1], ["mazda", 1], ["porsche", 1],
        ["skoda", 2], ["peugeot", 2], ["volvo", 2], ["alfa romeo", 2], ["saab", 2],
        ["dacia", 3], ["lada", 3], ["abarth", 3], ["koenigsegg", 3],
        ["caterham", 4], ["morgan", 4], ["ariel", 4], ["lucid", 4], ["gordon murray", 4],
        ["spyker", 5], ["ginetta", 5], ["rinspeed", 5], ["mosler", 5], ["tramontana", 5]
      ]
    },
    {
      q: "Name a cocktail",
      rules: "Classics and named modern cocktails both count.",
      a: [
        ["mojito", 0], ["margarita", 0], ["martini", 0], ["pina colada", 0],
        ["cosmopolitan", 1], ["bloody mary", 1], ["mimosa", 1],
        ["manhattan", 2], ["negroni", 2], ["daiquiri", 2], ["caipirinha", 2],
        ["sazerac", 3], ["gimlet", 3], ["tom collins", 3], ["rob roy", 3],
        ["aviation", 4], ["last word", 4], ["penicillin", 4], ["bramble", 4], ["paper plane", 4],
        ["hanky panky", 5], ["death in the afternoon", 5], ["charlie chaplin", 5], ["monkey gland", 5], ["tuxedo", 5]
      ]
    },
    {
      q: "Name a musical instrument",
      rules: "Played, blown, bowed or whisked — all families welcome.",
      a: [
        ["guitar", 0], ["piano", 0], ["drums", 0], ["violin", 0],
        ["flute", 1], ["trumpet", 1], ["saxophone", 1], ["clarinet", 1],
        ["cello", 2], ["trombone", 2], ["harp", 2], ["banjo", 2], ["harmonica", 2],
        ["oboe", 3], ["accordion", 3], ["sitar", 3], ["bagpipes", 3],
        ["didgeridoo", 4], ["theremin", 4], ["viola", 4], ["vibraphone", 4], ["crumhorn", 4],
        ["crwth", 5], ["nyckelharpa", 5], ["serpent", 5], ["ophicleide", 5], ["arghul", 5]
      ]
    },
    {
      q: "Name a river",
      rules: "Any real river, anywhere on Earth.",
      a: [
        ["nile", 0], ["amazon", 0], ["thames", 0], ["mississippi", 0],
        ["yangtze", 1], ["ganges", 1], ["danube", 1], ["mekong", 1],
        ["seine", 2], ["volga", 2], ["rhine", 2], ["colorado", 2], ["congo", 2],
        ["orinoco", 3], ["lena", 3], ["don", 3], ["yukon", 3],
        ["brahmaputra", 4], ["salween", 4], ["parana", 4], ["ob", 4], ["amur", 4],
        ["dniester", 5], ["sava", 5], ["pechora", 5], ["kolyma", 5], ["sungari", 5]
      ]
    },
    {
      q: "Name a dog breed",
      rules: "Kennel-club names preferred, nicknames accepted when unambiguous.",
      a: [
        ["labrador", 0], ["german shepherd", 0], ["poodle", 0], ["bulldog", 0],
        ["beagle", 1], ["rottweiler", 1], ["husky", 1], ["chihuahua", 1],
        ["boxer", 2], ["dachshund", 2], ["shih tzu", 2], ["greyhound", 2],
        ["basenji", 3], ["saluki", 3], ["keeshond", 3], ["otterhound", 3],
        ["kuvasz", 4], ["komondor", 4], ["spinone", 4], ["cirneco", 4], ["xoloitzcuintli", 4],
        ["mudi", 5], ["kooikerhondje", 5], ["sloughi", 5], ["azawakh", 5]
      ]
    },
    {
      q: "Name a type of cheese",
      rules: "Named cheeses count. Mouse-trap cheddar called just 'cheese' doesn't.",
      a: [
        ["cheddar", 0], ["mozzarella", 0], ["parmesan", 0], ["brie", 0],
        ["gouda", 1], ["feta", 1], ["edam", 1],
        ["camembert", 2], ["ricotta", 2], ["swiss", 2], ["halloumi", 2], ["mascarpone", 2],
        ["manchego", 3], ["gorgonzola", 3], ["provolone", 3], ["pecorino", 3],
        ["comte", 4], ["gruyere", 4], ["emmental", 4], ["caerphilly", 4], ["wensleydale", 4],
        ["tete de moine", 5], ["quark", 5], ["pont leveque", 5], ["livarot", 5]
      ]
    },
    {
      q: "Name an element on the periodic table",
      rules: "All 118 count. The back page of the table is where the points hide.",
      a: [
        ["gold", 0], ["iron", 0], ["oxygen", 0], ["helium", 0], ["carbon", 0],
        ["neon", 1], ["argon", 1], ["titanium", 1], ["silicon", 1], ["mercury", 1],
        ["lithium", 2], ["krypton", 2], ["chlorine", 2], ["potassium", 2], ["boron", 2],
        ["caesium", 3], ["beryllium", 3], ["selenium", 3], ["strontium", 3],
        ["gallium", 4], ["germanium", 4], ["tellurium", 4], ["samarium", 4], ["ytterbium", 4],
        ["berkelium", 5], ["dubnium", 5], ["hassium", 5], ["flerovium", 5], ["darmstadtium", 5]
      ]
    }
  ];
  window.LokiDiveBank = { tiers, prompts };
})();
