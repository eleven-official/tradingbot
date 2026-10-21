/* Loki Dive — rare-answer trivia bank.
 * Mechanic inspired by the daily game krillion.io, rebuilt original here:
 * every prompt takes one answer; the rarer the answer, the deeper you sink.
 * Answers are stored flat and lowercase; the engine folds diacritics and
 * punctuation, so "piña colada" matches either spelling — and gentle typos
 * are forgiven by the distance matcher in game.js.
 * Every entry is a real thing: real places, real species, real works, real
 * people, real names. Rarity tiers are editorial, not live statistics.
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
  /* [answer, tierIndex] pairs. Tier 0 is the most common, 5 the rarest. */
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
        ["seal", 2], ["starfish", 2], ["anglerfish", 2], ["walrus", 2],
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
      rules: "Played, blown, bowed or plucked — all families welcome.",
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
      rules: "Named cheeses count. Counter cheese called just 'cheese' doesn't.",
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
    },
    {
      q: "Name a country",
      rules: "UN members and widely recognised states count.",
      a: [
        ["france", 0], ["germany", 0], ["usa", 0], ["japan", 0], ["brazil", 0], ["australia", 0],
        ["canada", 1], ["spain", 1], ["italy", 1], ["india", 1], ["china", 1], ["mexico", 1],
        ["norway", 2], ["portugal", 2], ["greece", 2], ["egypt", 2], ["argentina", 2], ["kenya", 2],
        ["uruguay", 3], ["mongolia", 3], ["botswana", 3], ["nepal", 3], ["panama", 3],
        ["bhutan", 4], ["suriname", 4], ["djibouti", 4], ["lesotho", 4], ["timor leste", 4],
        ["kiribati", 5], ["tuvalu", 5], ["nauru", 5], ["sao tome and principe", 5], ["comoros", 5]
      ]
    },
    {
      q: "Name a capital city",
      rules: "Capital of a country — any country. Tiny pacific ones are pure gold.",
      a: [
        ["london", 0], ["paris", 0], ["tokyo", 0], ["washington dc", 0], ["rome", 0],
        ["berlin", 1], ["madrid", 1], ["moscow", 1], ["beijing", 1], ["canberra", 1],
        ["ottawa", 2], ["lisbon", 2], ["athens", 2], ["cairo", 2], ["dublin", 2], ["seoul", 2],
        ["reykjavik", 3], ["wellington", 3], ["hanoi", 3], ["lima", 3], ["nairobi", 3], ["caracas", 3],
        ["ulaanbaatar", 4], ["bishkek", 4], ["astana", 4], ["ouagadougou", 4], ["thimphu", 4], ["honiara", 4],
        ["ngerulmud", 5], ["yaren", 5], ["palikir", 5], ["sri jayawardenepura kotte", 5], ["vaiaku", 5]
      ]
    },
    {
      q: "Name a moon in the solar system",
      rules: "Ours counts too — but so do hundreds you have never met.",
      a: [
        ["the moon", 0], ["moon", 0],
        ["titan", 1], ["europa", 1], ["io", 1], ["ganymede", 1],
        ["callisto", 2], ["phobos", 2], ["deimos", 2], ["triton", 2], ["enceladus", 2],
        ["iapetus", 3], ["dione", 3], ["rhea", 3], ["tethys", 3], ["mimas", 3], ["ariel", 3],
        ["titania", 4], ["oberon", 4], ["umbriel", 4], ["nereid", 4], ["hyperion", 4], ["amalthea", 4],
        ["trinculo", 5], ["stephano", 5], ["prospero", 5], ["methone", 5], ["mab", 5]
      ]
    },
    {
      q: "Name a constellation",
      rules: "Official IAU constellations count — zodiac and far beyond.",
      a: [
        ["orion", 0], ["scorpio", 0],
        ["leo", 1], ["gemini", 1], ["libra", 1], ["virgo", 1], ["aquarius", 1],
        ["crux", 2], ["pegasus", 2], ["cygnus", 2], ["andromeda", 2], ["capricornus", 2],
        ["draco", 3], ["cepheus", 3], ["perseus", 3], ["aquila", 3], ["corvus", 3], ["lyra", 3],
        ["vela", 4], ["carina", 4], ["dorado", 4], ["grus", 4], ["tucana", 4], ["puppis", 4],
        ["vulpecula", 5], ["camelopardalis", 5], ["mensa", 5], ["chamaeleon", 5], ["antlia", 5]
      ]
    },
    {
      q: "Name a dinosaur",
      rules: "Famous prehistoric reptile cousins (pterosaurs, plesiosaurs) also count.",
      a: [
        ["tyrannosaurus rex", 0], ["triceratops", 0], ["stegosaurus", 0], ["velociraptor", 0],
        ["brachiosaurus", 1], ["pterodactyl", 1], ["allosaurus", 1], ["diplodocus", 1],
        ["spinosaurus", 2], ["ankylosaurus", 2], ["parasaurolophus", 2], ["plesiosaur", 2], ["archaeopteryx", 2],
        ["deinonychus", 3], ["carnotaurus", 3], ["iguanodon", 3], ["gallimimus", 3], ["utahraptor", 3],
        ["therizinosaurus", 4], ["amargasaurus", 4], ["cryolophosaurus", 4], ["concavenator", 4], ["majungasaurus", 4],
        ["dracorex", 5], ["einosaurus", 5], ["sinosauropteryx", 5], ["tarchia", 5], ["yi", 5]
      ]
    },
    {
      q: "Name a programming language",
      rules: "Real programming languages — markup like HTML doesn't count.",
      a: [
        ["python", 0], ["javascript", 0], ["java", 0],
        ["c", 1], ["cpp", 1], ["ruby", 1], ["php", 1], ["swift", 1], ["kotlin", 1],
        ["perl", 2], ["haskell", 2], ["lua", 2], ["fortran", 2], ["r", 2],
        ["clojure", 3], ["erlang", 3], ["prolog", 3], ["lisp", 3], ["ocaml", 3],
        ["crystal", 4], ["nim", 4], ["zig", 4], ["racket", 4], ["julia", 4],
        ["apl", 5], ["forth", 5], ["brainfuck", 5], ["intercal", 5], ["icon", 5]
      ]
    },
    {
      q: "Name a chess opening",
      rules: "Any named opening, gambit or defence. Yes, even the memes.",
      a: [
        ["sicilian defence", 0], ["queens gambit", 0],
        ["ruy lopez", 1], ["italian game", 1], ["french defence", 1], ["caro kann", 1],
        ["kings indian defence", 2], ["english opening", 2], ["kings gambit", 2], ["vienna game", 2], ["scandinavian defence", 2],
        ["grunfeld", 3], ["nimzo indian", 3], ["catalan", 3], ["slav defence", 3], ["fried liver attack", 3],
        ["bird", 4], ["berlin defence", 4], ["marshall attack", 4], ["albin counter gambit", 4],
        ["halloween gambit", 5], ["frankenstein dracula variation", 5], ["bongcloud attack", 5], ["stafford gambit", 5], ["englund gambit", 5]
      ]
    },
    {
      q: "Name a pasta shape",
      rules: "Dried, fresh, stuffed — shapes count, sauces don't.",
      a: [
        ["spaghetti", 0], ["penne", 0], ["macaroni", 0], ["lasagna", 0],
        ["fettuccine", 1], ["ravioli", 1], ["tagliatelle", 1], ["linguine", 1],
        ["rigatoni", 2], ["farfalle", 2], ["orzo", 2], ["cannelloni", 2], ["gnocchi", 2],
        ["bucatini", 3], ["orecchiette", 3], ["pappardelle", 3], ["cavatappi", 3], ["trofie", 3],
        ["strozzapreti", 4], ["mafaldine", 4], ["casarecce", 4], ["paccheri", 4], ["anelletti", 4],
        ["culurgiones", 5], ["corzetti", 5], ["bigoli", 5], ["scialatielli", 5], ["fregola", 5]
      ]
    },
    {
      q: "Name a pizza topping",
      rules: "Anything that has actually been put on a pizza.",
      a: [
        ["pepperoni", 0], ["cheese", 0], ["mushroom", 0], ["sausage", 0],
        ["pineapple", 1], ["bacon", 1], ["olive", 1], ["onion", 1],
        ["spinach", 2], ["feta", 2], ["jalapeno", 2], ["anchovy", 2],
        ["prosciutto", 3], ["arugula", 3], ["artichoke", 3], ["capicola", 3],
        ["gorgonzola", 4], ["truffle", 4], ["capers", 4], ["nduja", 4],
        ["guanciale", 5], ["bottarga", 5], ["quail egg", 5], ["shiso", 5]
      ]
    },
    {
      q: "Name an ice cream flavour",
      rules: "Shop-counter flavours count. The braver the shop, the deeper you sink.",
      a: [
        ["vanilla", 0], ["chocolate", 0], ["strawberry", 0],
        ["mint chocolate chip", 1], ["cookies and cream", 1], ["cookie dough", 1],
        ["pistachio", 2], ["rocky road", 2], ["neapolitan", 2], ["butter pecan", 2],
        ["salted caramel", 3], ["black sesame", 3], ["spumoni", 3], ["taro", 3],
        ["ube", 4], ["kulfi", 4], ["halva", 4], ["stracciatella", 4],
        ["brown bread", 5], ["garlic", 5], ["ghost pepper", 5], ["marmite", 5]
      ]
    },
    {
      q: "Name a fast food chain",
      rules: "Counter restaurants count, drive-thrus count, the obscure locals definitely count.",
      a: [
        ["mcdonalds", 0], ["burger king", 0], ["kfc", 0],
        ["subway", 1], ["taco bell", 1], ["pizza hut", 1], ["wendys", 1],
        ["dominos", 2], ["chick fil a", 2], ["papa johns", 2], ["panera bread", 2],
        ["arbys", 3], ["in n out", 3], ["dairy queen", 3], ["quiznos", 3],
        ["del taco", 4], ["culvers", 4], ["white castle", 4], ["waffle house", 4], ["au bon pain", 4],
        ["zaxbys", 5], ["biscuitville", 5], ["dicks drive in", 5], ["krystal", 5]
      ]
    },
    {
      q: "Name a video game",
      rules: "Any era, any platform — arcade cabinets to hand-helds.",
      a: [
        ["super mario", 0], ["pac man", 0], ["tetris", 0],
        ["minecraft", 1], ["zelda", 1], ["fortnite", 1], ["pong", 1],
        ["sonic", 2], ["street fighter", 2], ["donkey kong", 2], ["resident evil", 2], ["overwatch", 2],
        ["metroid", 3], ["castlevania", 3], ["dark souls", 3], ["final fantasy", 3], ["tekken", 3],
        ["celeste", 4], ["hollow knight", 4], ["undertale", 4], ["outer wilds", 4], ["disco elysium", 4],
        ["shaq fu", 5], ["superman 64", 5], ["big rigs over the road racing", 5], ["bubsy 3d", 5]
      ]
    },
    {
      q: "Name a board game",
      rules: "Board and table games count — a casual card game counts too.",
      a: [
        ["monopoly", 0], ["chess", 0], ["checkers", 0],
        ["scrabble", 1], ["uno", 1], ["battleship", 1], ["clue", 1],
        ["risk", 2], ["stratego", 2], ["backgammon", 2], ["jenga", 2],
        ["ticket to ride", 3], ["carcassonne", 3], ["pandemic", 3], ["puerto rico", 3],
        ["dominion", 4], ["patchwork", 4], ["azul", 4], ["wingspan", 4], ["cascadia", 4],
        ["twilight struggle", 5], ["brass birmingham", 5], ["through the ages", 5], ["agricola", 5]
      ]
    },
    {
      q: "Name a superhero from comics",
      rules: "Any comic publisher — indies count extra.",
      a: [
        ["superman", 0], ["batman", 0], ["spiderman", 0], ["hulk", 0],
        ["iron man", 1], ["wonder woman", 1], ["thor", 1], ["captain america", 1],
        ["wolverine", 2], ["flash", 2], ["green lantern", 2], ["aquaman", 2], ["black panther", 2],
        ["doctor strange", 3], ["silver surfer", 3], ["moon knight", 3], ["spawn", 3], ["invincible", 3],
        ["hellboy", 4], ["judge dredd", 4], ["usagi yojimbo", 4], ["savage dragon", 4],
        ["the maxx", 5], ["squirrel girl", 5], ["madman", 5], ["manhunter", 5]
      ]
    },
    {
      q: "Name a Simpsons character",
      rules: "Springfield residents count, even one-appearance ones.",
      a: [
        ["homer", 0], ["bart", 0], ["marge", 0], ["lisa", 0],
        ["maggie", 1], ["mr burns", 1], ["ned flanders", 1], ["moe", 1],
        ["krusty", 2], ["milhouse", 2], ["apu", 2], ["chief wiggum", 2], ["barney", 2],
        ["smithers", 3], ["lenny", 3], ["carl", 3], ["patty", 3], ["selma", 3],
        ["duffman", 4], ["lionel hutz", 4], ["troy mcclure", 4], ["disco stu", 4], ["hans moleman", 4],
        ["frank grimes", 5], ["shary bobbins", 5], ["poochie", 5], ["lurleen lumpkin", 5]
      ]
    },
    {
      q: "Name a Studio Ghibli film",
      rules: "Films made under the Ghibli banner count.",
      a: [
        ["my neighbour totoro", 0], ["my neighbor totoro", 0], ["spirited away", 0],
        ["princess mononoke", 1], ["hows moving castle", 1], ["ponyo", 1], ["kikis delivery service", 1],
        ["castle in the sky", 2], ["grave of the fireflies", 2], ["porco rosso", 2], ["whisper of the heart", 2],
        ["only yesterday", 3], ["pom poko", 3], ["ocean waves", 3], ["my neighbors the yamadas", 3],
        ["the tale of the princess kaguya", 4], ["from up on poppy hill", 4], ["the wind rises", 4],
        ["the red turtle", 5], ["earwig and the witch", 5]
      ]
    },
    {
      q: "Name a Star Wars character",
      rules: "Any canon or legends character — the podrace crowd counts.",
      a: [
        ["darth vader", 0], ["luke skywalker", 0], ["yoda", 0], ["han solo", 0], ["princess leia", 0],
        ["chewbacca", 1], ["obi wan kenobi", 1], ["r2d2", 1], ["c3po", 1],
        ["boba fett", 2], ["lando", 2], ["palpatine", 2], ["jabba the hutt", 2], ["admiral ackbar", 2],
        ["grand moff tarkin", 3], ["wedge antilles", 3], ["biggs darklighter", 3], ["mon mothma", 3],
        ["bossk", 4], ["dengar", 4], ["zuckuss", 4], ["4 lom", 4], ["ig 88", 4],
        ["gasgano", 5], ["dud bolt", 5], ["ody mandrell", 5], ["mars guo", 5]
      ]
    },
    {
      q: "Name a Beatles song",
      rules: "Album tracks and b-sides score the depths.",
      a: [
        ["let it be", 0], ["hey jude", 0], ["yesterday", 0],
        ["come together", 1], ["blackbird", 1], ["twist and shout", 1], ["drive my car", 1],
        ["in my life", 2], ["norwegian wood", 2], ["being for the benefit of mr kite", 2], ["i am the walrus", 2],
        ["she said she said", 3], ["tomorrow never knows", 3], ["mean mr mustard", 3], ["polythene pam", 3], ["cry baby cry", 3],
        ["wild honey pie", 4], ["the continuing story of bungalow bill", 4], ["her majesty", 4], ["good night", 4],
        ["dig it", 5], ["maggie mae", 5], ["you know my name look up the number", 5], ["flying", 5]
      ]
    },
    {
      q: "Name a classical composer",
      rules: "From the baroque to the modern concert hall.",
      a: [
        ["mozart", 0], ["beethoven", 0], ["bach", 0],
        ["chopin", 1], ["tchaikovsky", 1], ["vivaldi", 1], ["liszt", 1],
        ["handel", 2], ["haydn", 2], ["wagner", 2], ["debussy", 2],
        ["rachmaninoff", 3], ["shostakovich", 3], ["mahler", 3], ["sibelius", 3], ["saint saens", 3],
        ["corelli", 4], ["albinoni", 4], ["bruckner", 4], ["arvo part", 4], ["enescu", 4],
        ["sofia gubaidulina", 5], ["allan petterson", 5], ["zelenka", 5], ["biber", 5]
      ]
    },
    {
      q: "Name a famous painter",
      rules: "Painters and visual artists — past or present, any movement.",
      a: [
        ["van gogh", 0], ["picasso", 0], ["monet", 0], ["da vinci", 0],
        ["rembrandt", 1], ["dali", 1], ["frida kahlo", 1], ["michelangelo", 1],
        ["vermeer", 2], ["klimt", 2], ["kandinsky", 2], ["pollock", 2], ["banksy", 2],
        ["klee", 3], ["magritte", 3], ["mondrian", 3], ["hopper", 3], ["basquiat", 3],
        ["egon schiele", 4], ["tamara de lempicka", 4], ["hieronymus bosch", 4], ["goya", 4],
        ["hilma af klint", 5], ["arcimboldo", 5], ["yves klein", 5], ["malevich", 5]
      ]
    },
    {
      q: "Name a philosopher",
      rules: "Anyone who writes big ideas — ancient or modern, East or West.",
      a: [
        ["plato", 0], ["aristotle", 0], ["socrates", 0],
        ["kant", 1], ["nietzsche", 1], ["descartes", 1],
        ["hume", 2], ["hegel", 2], ["marx", 2], ["spinoza", 2], ["locke", 2],
        ["kierkegaard", 3], ["epictetus", 3], ["marcus aurelius", 3], ["seneca", 3], ["aquinas", 3],
        ["zhuangzi", 4], ["ibn sina", 4], ["meister eckhart", 4], ["wang yangming", 4],
        ["parmenides", 5], ["protagoras", 5], ["gorgias", 5], ["hypatia", 5]
      ]
    },
    {
      q: "Name a scientist",
      rules: "Any field — physics to genetics to computers.",
      a: [
        ["einstein", 0], ["newton", 0], ["marie curie", 0],
        ["darwin", 1], ["galileo", 1], ["tesla", 1], ["hawking", 1],
        ["mendel", 2], ["planck", 2], ["faraday", 2], ["bohr", 2], ["ada lovelace", 2],
        ["lavoisier", 3], ["feynman", 3], ["maxwell", 3], ["linnaeus", 3], ["fleming", 3],
        ["barbara mcclintock", 4], ["tu youyou", 4], ["al khwarizmi", 4], ["ibn al haytham", 4],
        ["eunice newton foote", 5], ["milankovitch", 5], ["osborne reynolds", 5], ["kathleen lonsdale", 5]
      ]
    },
    {
      q: "Name an Olympic sport",
      rules: "Modern or former medal sports — the 1900 programme had surprises.",
      a: [
        ["swimming", 0], ["athletics", 0], ["gymnastics", 0],
        ["fencing", 1], ["rowing", 1], ["judo", 1], ["archery", 1], ["boxing", 1],
        ["taekwondo", 2], ["biathlon", 2], ["curling", 2], ["luge", 2], ["skeleton", 2],
        ["equestrian", 3], ["modern pentathlon", 3], ["greco roman wrestling", 3], ["hammer throw", 3], ["canoe slalom", 3],
        ["rhythmic gymnastics", 4], ["artistic swimming", 4], ["handball", 4], ["breaking", 4],
        ["tug of war", 5], ["croquet", 5], ["jeu de paume", 5], ["roque", 5], ["basque pelota", 5]
      ]
    },
    {
      q: "Name a football (soccer) club",
      rules: "Any club, any league, any century. Scottish lower leagues count.",
      a: [
        ["manchester united", 0], ["real madrid", 0], ["barcelona", 0], ["liverpool", 0],
        ["arsenal", 1], ["chelsea", 1], ["bayern munich", 1], ["juventus", 1],
        ["napoli", 2], ["ajax", 2], ["porto", 2], ["celtic", 2], ["galatasaray", 2],
        ["psv", 3], ["sporting cp", 3], ["red star belgrade", 3], ["dynamo kyiv", 3], ["rangers", 3],
        ["steaua bucharest", 4], ["maccabi haifa", 4], ["boavista", 4], ["kilmarnock", 4],
        ["queen of the south", 5], ["albion rovers", 5], ["berwick rangers", 5], ["annan athletic", 5]
      ]
    },
    {
      q: "Name a martial art",
      rules: "Any named system of fighting, anywhere, any era.",
      a: [
        ["karate", 0], ["boxing", 0],
        ["taekwondo", 1], ["jiu jitsu", 1], ["kung fu", 1], ["wrestling", 1],
        ["muay thai", 2], ["capoeira", 2], ["aikido", 2], ["krav maga", 2],
        ["wing chun", 3], ["hapkido", 3], ["sumo", 3], ["kendo", 3],
        ["sambo", 4], ["jeet kune do", 4], ["iaido", 4], ["silat", 4],
        ["kalaripayattu", 5], ["systema", 5], ["jogo do pau", 5], ["singlestick", 5]
      ]
    },
    {
      q: "Name a coffee drink",
      rules: "Found on a menu anywhere in the world.",
      a: [
        ["espresso", 0], ["latte", 0], ["cappuccino", 0], ["americano", 0],
        ["mocha", 1], ["flat white", 1], ["macchiato", 1], ["black coffee", 1],
        ["cortado", 2], ["ristretto", 2], ["affogato", 2], ["turkish coffee", 2],
        ["irish coffee", 3], ["galao", 3], ["cuban coffee", 3], ["kopi luwak", 3], ["frappuccino", 3],
        ["cascara", 4], ["shakerato", 4], ["carajillo", 4], ["espresso romano", 4],
        ["kaffeost", 5], ["cafe de olla", 5], ["mazagran", 5], ["einspanner", 5]
      ]
    },
    {
      q: "Name a sandwich",
      rules: "Bread plus filling, anywhere on Earth — including national treasures.",
      a: [
        ["blt", 0], ["club sandwich", 0], ["grilled cheese", 0], ["peanut butter and jelly", 0],
        ["reuben", 1], ["cheesesteak", 1], ["cuban sandwich", 1], ["cuban", 1], ["pbj", 1],
        ["muffuletta", 2], ["banh mi", 2], ["sloppy joe", 2], ["tuna melt", 2],
        ["torta", 3], ["katsu sando", 3], ["po boy", 3], ["egg salad sandwich", 3],
        ["chacarero", 4], ["vada pav", 4], ["smorrebrod", 4], ["croque madame", 4],
        ["francesinha", 5], ["smorgastarta", 5], ["strammer max", 5], ["guajolota", 5]
      ]
    },
    {
      q: "Name a soup",
      rules: "Any soup, chilled or hot — national classics welcome.",
      a: [
        ["tomato soup", 0], ["chicken noodle", 0], ["miso", 0],
        ["minestrone", 1], ["gazpacho", 1], ["french onion", 1], ["wonton", 1],
        ["clam chowder", 2], ["borscht", 2], ["tom yum", 2], ["pho", 2],
        ["vichyssoise", 3], ["gumbo", 3], ["laksa", 3], ["harira", 3], ["egusi", 3],
        ["mulligatawny", 4], ["caldo verde", 4], ["garbure", 4], ["kharcho", 4],
        ["shchi", 5], ["samgyetang", 5], ["locro", 5], ["caldo de piedra", 5]
      ]
    },
    {
      q: "Name a mountain range",
      rules: "Real ranges anywhere on the planet.",
      a: [
        ["himalayas", 0], ["alps", 0], ["rocky mountains", 0], ["the rockies", 1], ["andes", 1], ["urals", 1],
        ["appalachians", 2], ["pyrenees", 2], ["caucasus", 2], ["atlas", 2], ["sierra nevada", 2],
        ["carpathians", 3], ["altai", 3], ["hindu kush", 3], ["tatra", 3], ["cantabrian", 3],
        ["sudetes", 4], ["vindhyas", 4], ["jura", 4], ["balkan mountains", 4], ["pindus", 4],
        ["chugach", 5], ["wrangell mountains", 5], ["alborz", 5], ["sudirman", 5], ["atalaya", 5]
      ]
    },
    {
      q: "Name a desert",
      rules: "Hot or cold, sand or rock — real deserts only.",
      a: [
        ["sahara", 0], ["gobi", 0],
        ["kalahari", 1], ["namib", 1], ["atacama", 1], ["sonoran", 1],
        ["mojave", 2], ["arabian", 2], ["arabian desert", 2], ["karakum", 2], ["great victoria desert", 2],
        ["rub al khali", 3], ["gibson desert", 3], ["great sandy desert", 3], ["chihuahuan desert", 3], ["thar", 3],
        ["dasht e lut", 4], ["nubian desert", 4], ["syrian desert", 4], ["wahiba sands", 4], ["great basin", 4],
        ["kyzylkum", 5], ["strzelecki desert", 5], ["painted desert", 5], ["tanami desert", 5], ["simpson desert", 5]
      ]
    },
    {
      q: "Name a US president",
      rules: "Any president — including the barely remembered ones.",
      a: [
        ["george washington", 0], ["abraham lincoln", 0], ["barack obama", 0],
        ["thomas jefferson", 1], ["john f kennedy", 1], ["jfk", 1], ["franklin roosevelt", 1], ["teddy roosevelt", 1],
        ["harry truman", 2], ["eisenhower", 2], ["ronald reagan", 2], ["andrew jackson", 2], ["ulysses s grant", 2],
        ["herbert hoover", 3], ["calvin coolidge", 3], ["james madison", 3], ["woodrow wilson", 3], ["william howard taft", 3],
        ["william henry harrison", 4], ["zachary taylor", 4], ["james garfield", 4], ["gerald ford", 4],
        ["millard fillmore", 5], ["franklin pierce", 5], ["chester arthur", 5], ["martin van buren", 5]
      ]
    },
    {
      q: "Name a colour",
      rules: "Real colour names — not just the rainbow. Obscure ones are treasure.",
      a: [
        ["red", 0], ["blue", 0], ["green", 0], ["yellow", 0],
        ["purple", 1], ["orange", 1], ["pink", 1], ["black", 1], ["white", 1],
        ["teal", 2], ["maroon", 2], ["lavender", 2], ["turquoise", 2], ["magenta", 2],
        ["mauve", 3], ["cerulean", 3], ["vermilion", 3], ["ochre", 3], ["chartreuse", 3],
        ["burgundy", 4], ["taupe", 4], ["lilac", 4], ["phthalo", 4], ["indigo", 4],
        ["smaragdine", 5], ["incarnadine", 5], ["sarcoline", 5], ["coquelicot", 5], ["xanadu", 5]
      ]
    },
    {
      q: "Name a tree",
      rules: "Any real species, rainforest to back garden.",
      a: [
        ["oak", 0], ["pine", 0], ["maple", 0], ["birch", 0],
        ["willow", 1], ["cedar", 1], ["spruce", 1], ["beech", 1],
        ["redwood", 2], ["sequoia", 2], ["chestnut", 2], ["poplar", 2], ["alder", 2],
        ["baobab", 3], ["mangrove", 3], ["larch", 3], ["yew", 3],
        ["catalpa", 4], ["hornbeam", 4], ["rowan", 4], ["kauri", 4], ["tulip tree", 4],
        ["monkey puzzle", 5], ["dragon tree", 5], ["sundari", 5], ["bristlecone", 5], ["cork elm", 5]
      ]
    },
    {
      q: "Name a mountain",
      rules: "Real peaks anywhere on Earth — the eight-thousanders hide in the deep tiers.",
      a: [
        ["everest", 0], ["mount everest", 0], ["kilimanjaro", 0],
        ["denali", 1], ["k2", 1], ["mont blanc", 1], ["fuji", 1], ["mckinley", 1],
        ["matterhorn", 2], ["elbrus", 2], ["annapurna", 2], ["kangchenjunga", 2], ["ben nevis", 2],
        ["lhotse", 3], ["makalu", 3], ["ama dablam", 3], ["dhaulagiri", 3], ["gasherbrum", 3], ["broad peak", 3],
        ["shishapangma", 4], ["nanga parbat", 4], ["rakaposhi", 4], ["masherbrum", 4], ["cho oyu", 4],
        ["spantik", 5], ["khan tengri", 5], ["ultar sar", 5], ["malubiting", 5], ["muztagh ata", 5]
      ]
    },
    {
      q: "Name a sea",
      rules: "A salt-water sea on the map; salt ponds and bays don't qualify.",
      a: [
        ["mediterranean", 0], ["baltic", 0], ["red sea", 0], ["dead sea", 0],
        ["caribbean", 1], ["black sea", 1], ["caspian", 1],
        ["north sea", 2], ["bering", 2], ["adriatic", 2], ["aegean", 2],
        ["sargasso", 3], ["barents", 3], ["coral sea", 3], ["tasman", 3],
        ["weddell", 4], ["okhotsk", 4], ["white sea", 4], ["azov", 4],
        ["laptev", 5], ["beaufort", 5], ["celebes", 5], ["amundsen", 5]
      ]
    },
    {
      q: "Name a currency",
      rules: "A real money name in active use beats a collector's coin.",
      a: [
        ["dollar", 0], ["euro", 0], ["yen", 0], ["rupee", 0], ["pound", 0],
        ["yuan", 1], ["ruble", 1], ["franc", 1], ["real", 1], ["riyal", 1], ["krona", 1],
        ["peso", 2], ["zloty", 2], ["forint", 2], ["baht", 2], ["krone", 2],
        ["dinar", 3], ["dong", 3], ["sol", 3], ["birr", 3], ["dirham", 3],
        ["tenge", 4], ["quetzal", 4], ["lempira", 4], ["lev", 4],
        ["rufiyaa", 5], ["ariary", 5], ["ouguiya", 5], ["gourde", 5], ["dalasi", 5]
      ]
    },
    {
      q: "Name a sushi item",
      rules: "Something a sushi bar actually serves — real plates only.",
      a: [
        ["tuna", 0], ["salmon", 0], ["nigiri", 0],
        ["california roll", 1], ["tamago", 1], ["wakame", 1], ["shrimp", 1], ["spicy tuna roll", 1],
        ["unagi", 2], ["ikura", 2], ["uni", 2], ["mackerel", 2],
        ["otoro", 3], ["hamachi", 3], ["ankimo", 3], ["temaki", 3],
        ["fugu", 4], ["kohada", 4], ["chirashi", 4], ["tobiko", 4],
        ["shirako", 5], ["aburi", 5], ["namerou", 5], ["gomae", 5]
      ]
    },
    {
      q: "Name a fighter jet",
      rules: "A real military fighter aircraft, any era — trainers don't count.",
      a: [
        ["spitfire", 0], ["f 16", 0],
        ["mig 21", 1], ["f 22", 1], ["harrier", 1], ["typhoon", 1],
        ["mirage", 2], ["sabre", 2], ["corsair", 2], ["rafale", 2], ["tornado", 2],
        ["viggen", 3], ["draken", 3], ["phantom", 3], ["starfighter", 3],
        ["gripen", 4], ["flanker", 4], ["fulcrum", 4], ["shinden", 4],
        ["kfir", 5], ["flagon", 5], ["fishbed", 5]
      ]
    },
    {
      q: "Name a tea",
      rules: "A true tea or a tisane people steep on purpose.",
      a: [
        ["earl grey", 0], ["green tea", 0], ["black tea", 0], ["chamomile", 0],
        ["peppermint", 1], ["oolong", 1], ["jasmine", 1], ["english breakfast", 1],
        ["sencha", 2], ["matcha", 2], ["rooibos", 2], ["chai", 2],
        ["lapsang souchong", 3], ["darjeeling", 3], ["assam", 3], ["genmaicha", 3],
        ["gyokuro", 4], ["silver needle", 4], ["pu erh", 4], ["hojicha", 4],
        ["dan cong", 5], ["dianhong", 5], ["yuanyang", 5], ["london fog", 5]
      ]
    },
    {
      q: "Name a typeface",
      rules: "A real released typeface — no generic kinds of font.",
      a: [
        ["arial", 0], ["times new roman", 0], ["calibri", 0], ["comic sans", 0], ["helvetica", 0],
        ["courier", 1], ["futura", 1], ["verdana", 1], ["garamond", 1],
        ["baskerville", 2], ["caslon", 2], ["tahoma", 2], ["gill sans", 2],
        ["bodoni", 3], ["didot", 3], ["optima", 3], ["univers", 3],
        ["frutiger", 4], ["rockwell", 4], ["franklin gothic", 4], ["inter", 4],
        ["akzidenz grotesk", 5], ["cooper black", 5], ["papyrus", 5], ["benguiat", 5]
      ]
    },
    {
      q: "Name a Norse god",
      rules: "From the old Norse canon — not the MCU cast list.",
      a: [
        ["odin", 0], ["loki", 0], ["freya", 0],
        ["frigg", 1], ["baldr", 1], ["heimdall", 1], ["tyr", 1],
        ["njord", 2], ["bragi", 2], ["freyr", 2], ["sif", 2], ["hel", 2],
        ["forseti", 3], ["mimir", 3], ["hoenir", 3],
        ["vali", 4], ["vidar", 4], ["gefjon", 4], ["lofn", 4],
        ["kvasir", 5], ["vili", 5], ["gullveig", 5], ["syn", 5], ["ve", 5]
      ]
    }
  ];
  window.LokiDiveBank = { tiers, prompts };
})();
