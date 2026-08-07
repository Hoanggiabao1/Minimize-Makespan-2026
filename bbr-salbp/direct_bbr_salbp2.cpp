// Independent reimplementation of the direct BBR algorithm for SALBP-2.
//
// Algorithmic reference:
// E. Alvarez-Miranda, J. Pereira, and M. Vila,
// "A branch, bound and remember algorithm for maximizing the production rate
// in the simple assembly line balancing problem",
// Computers & Operations Research 166 (2024) 106597.
//
// The original SALBP-1 program in this repository is intentionally left
// untouched.  This file builds a separate executable.

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <optional>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace direct_bbr {

using Clock = std::chrono::steady_clock;
constexpr int INF = std::numeric_limits<int>::max() / 4;

std::string trim(const std::string &s) {
  const auto first = s.find_first_not_of(" \t\r\n");
  if (first == std::string::npos) return "";
  const auto last = s.find_last_not_of(" \t\r\n");
  return s.substr(first, last - first + 1);
}

std::string lower(std::string s) {
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
    return static_cast<char>(std::tolower(c));
  });
  return s;
}

int ceil_div_nonnegative(long long a, long long b) {
  if (b <= 0 || a < 0) throw std::logic_error("invalid nonnegative ceil division");
  return static_cast<int>((a + b - 1) / b);
}

long long ceil_div_signed(long long a, long long b) {
  if (b <= 0) throw std::logic_error("invalid signed ceil division");
  if (a >= 0) return (a + b - 1) / b;
  // C++ truncation toward zero is ceiling for a negative numerator.
  return a / b;
}

struct Options {
  std::string input;
  int stations = -1;
  double time_limit = 600.0;
  std::size_t memory_states = 60000000ULL;
  std::size_t max_extensions = 10000ULL;
  bool generalized_jackson = true;
  bool dominance_rules = true;
  bool lm4_root = true;
  bool lm4_search = false;
  bool quiet = false;
  std::string csv_output;
  std::string solution_output;
};

struct Instance {
  std::string name;
  int n = 0;
  int m = 0;
  std::vector<int> time;
  std::vector<std::vector<int>> pred;
  std::vector<std::vector<int>> succ;
  std::vector<int> topo;
  std::vector<int> topo_position;
  std::vector<std::vector<std::uint64_t>> transitive_succ;
  std::vector<std::vector<unsigned char>> dominates;
  std::vector<int> positional_weight;
  int total_time = 0;
  int max_time = 0;
};

std::vector<int> parse_ints(std::string line) {
  for (char &c : line) {
    if (c == ',' || c == ';' || c == '\t') c = ' ';
  }
  std::stringstream ss(line);
  std::vector<int> result;
  int x;
  while (ss >> x) result.push_back(x);
  return result;
}

void add_edge(std::vector<std::pair<int, int>> &edges, int a, int b, int n,
              const std::string &source) {
  if (a == -1 && b == -1) return;
  if (a < 1 || a > n || b < 1 || b > n || a == b) {
    throw std::runtime_error("invalid precedence relation in " + source + ": " +
                             std::to_string(a) + "," + std::to_string(b));
  }
  edges.emplace_back(a - 1, b - 1);
}

Instance read_instance(const Options &opt) {
  std::ifstream in(opt.input);
  if (!in) throw std::runtime_error("cannot open input file: " + opt.input);

  std::vector<std::string> lines;
  std::string line;
  bool tagged = false;
  while (std::getline(in, line)) {
    line = trim(line);
    if (line.empty()) continue;
    if (!line.empty() && line.front() == '<') tagged = true;
    lines.push_back(line);
  }
  if (lines.empty()) throw std::runtime_error("empty input file: " + opt.input);

  Instance inst;
  inst.name = opt.input;
  std::vector<std::pair<int, int>> edges;

  if (!tagged) {
    const auto first = parse_ints(lines.front());
    if (first.size() != 1 || first[0] <= 0)
      throw std::runtime_error("invalid IN2 task count");
    inst.n = first[0];
    if (static_cast<int>(lines.size()) < inst.n + 1)
      throw std::runtime_error("IN2 file ends before all task times are read");
    inst.time.resize(inst.n);
    for (int i = 0; i < inst.n; ++i) {
      const auto values = parse_ints(lines[i + 1]);
      if (values.size() != 1 || values[0] <= 0)
        throw std::runtime_error("invalid IN2 task time on task " +
                                 std::to_string(i + 1));
      inst.time[i] = values[0];
    }
    for (std::size_t i = static_cast<std::size_t>(inst.n + 1);
         i < lines.size(); ++i) {
      const auto values = parse_ints(lines[i]);
      if (values.size() < 2) continue;
      if (values[0] == -1 && values[1] == -1) break;
      add_edge(edges, values[0], values[1], inst.n, opt.input);
    }
    inst.m = opt.stations;
  } else {
    enum class Section { NONE, N_TASKS, N_STATIONS, TASK_TIMES, PRECEDENCE };
    Section section = Section::NONE;
    std::vector<std::pair<int, int>> task_times;
    for (const std::string &raw : lines) {
      if (raw.front() == '<') {
        const std::string tag = lower(raw);
        if (tag.find("number of tasks") != std::string::npos)
          section = Section::N_TASKS;
        else if (tag.find("number of stations") != std::string::npos)
          section = Section::N_STATIONS;
        else if (tag.find("task times") != std::string::npos)
          section = Section::TASK_TIMES;
        else if (tag.find("precedence") != std::string::npos)
          section = Section::PRECEDENCE;
        else
          section = Section::NONE;
        continue;
      }
      const auto values = parse_ints(raw);
      if (values.empty()) continue;
      switch (section) {
        case Section::N_TASKS:
          inst.n = values[0];
          section = Section::NONE;
          break;
        case Section::N_STATIONS:
          inst.m = values[0];
          section = Section::NONE;
          break;
        case Section::TASK_TIMES:
          if (values.size() >= 2) task_times.emplace_back(values[0], values[1]);
          break;
        case Section::PRECEDENCE:
          if (values.size() >= 2 && !(values[0] == -1 && values[1] == -1))
            edges.emplace_back(values[0] - 1, values[1] - 1);
          break;
        default:
          break;
      }
    }
    if (inst.n <= 0) throw std::runtime_error("missing <number of tasks>");
    inst.time.assign(inst.n, -1);
    for (const auto &[id, value] : task_times) {
      if (id < 1 || id > inst.n || value <= 0)
        throw std::runtime_error("invalid task-time row in " + opt.input);
      if (inst.time[id - 1] != -1)
        throw std::runtime_error("duplicate task time for task " +
                                 std::to_string(id));
      inst.time[id - 1] = value;
    }
    if (std::find(inst.time.begin(), inst.time.end(), -1) != inst.time.end())
      throw std::runtime_error("not all task times were provided");
    if (opt.stations > 0) inst.m = opt.stations;
    for (const auto &[a, b] : edges) {
      if (a < 0 || a >= inst.n || b < 0 || b >= inst.n || a == b)
        throw std::runtime_error("invalid precedence relation in " + opt.input);
    }
  }

  if (inst.m <= 0)
    throw std::runtime_error(
        "number of stations is missing; supply --stations M for IN2 files");
  if (inst.n <= 0 || static_cast<int>(inst.time.size()) != inst.n)
    throw std::runtime_error("invalid instance dimensions");

  std::sort(edges.begin(), edges.end());
  edges.erase(std::unique(edges.begin(), edges.end()), edges.end());
  inst.pred.assign(inst.n, {});
  inst.succ.assign(inst.n, {});
  for (const auto &[a, b] : edges) {
    inst.succ[a].push_back(b);
    inst.pred[b].push_back(a);
  }

  std::vector<int> indegree(inst.n);
  std::priority_queue<int, std::vector<int>, std::greater<int>> ready;
  for (int i = 0; i < inst.n; ++i) {
    indegree[i] = static_cast<int>(inst.pred[i].size());
    if (indegree[i] == 0) ready.push(i);
  }
  while (!ready.empty()) {
    int i = ready.top();
    ready.pop();
    inst.topo.push_back(i);
    for (int j : inst.succ[i])
      if (--indegree[j] == 0) ready.push(j);
  }
  if (static_cast<int>(inst.topo.size()) != inst.n)
    throw std::runtime_error("precedence graph contains a directed cycle");
  inst.topo_position.resize(inst.n);
  for (int p = 0; p < inst.n; ++p) inst.topo_position[inst.topo[p]] = p;

  inst.total_time = std::accumulate(inst.time.begin(), inst.time.end(), 0);
  inst.max_time = *std::max_element(inst.time.begin(), inst.time.end());

  const int words = (inst.n + 63) / 64;
  inst.transitive_succ.assign(inst.n, std::vector<std::uint64_t>(words, 0));
  for (auto it = inst.topo.rbegin(); it != inst.topo.rend(); ++it) {
    const int i = *it;
    for (int j : inst.succ[i]) {
      inst.transitive_succ[i][j / 64] |= (std::uint64_t{1} << (j % 64));
      for (int w = 0; w < words; ++w)
        inst.transitive_succ[i][w] |= inst.transitive_succ[j][w];
    }
  }

  inst.dominates.assign(inst.n, std::vector<unsigned char>(inst.n, 0));
  for (int i = 0; i < inst.n; ++i) {
    for (int j = 0; j < inst.n; ++j) {
      if (i == j) continue;
      const bool i_before_j =
          (inst.transitive_succ[i][j / 64] >> (j % 64)) & 1U;
      const bool j_before_i =
          (inst.transitive_succ[j][i / 64] >> (i % 64)) & 1U;
      if (i_before_j || j_before_i) continue;
      bool superset = true;
      for (int w = 0; w < words; ++w) {
        if ((inst.transitive_succ[j][w] & ~inst.transitive_succ[i][w]) != 0) {
          superset = false;
          break;
        }
      }
      if (superset &&
          (inst.time[i] > inst.time[j] ||
           (inst.time[i] == inst.time[j] && i < j)))
        inst.dominates[i][j] = 1;
    }
  }

  inst.positional_weight = inst.time;
  for (int i = 0; i < inst.n; ++i) {
    for (int j = 0; j < inst.n; ++j) {
      if ((inst.transitive_succ[i][j / 64] >> (j % 64)) & 1U)
        inst.positional_weight[i] += inst.time[j];
    }
  }
  return inst;
}

struct BoundBreakdown {
  int lb1 = 0;
  int lb2 = 0;
  int lm2 = 0;
  int lm3 = 0;
  int l3 = 0;
  int lm4 = 0;
  int combined = 0;
};

int parallel_lb1(const std::vector<int> &times, int stations) {
  if (times.empty()) return 0;
  if (stations <= 0) return INF;
  const int sum = std::accumulate(times.begin(), times.end(), 0);
  const int largest = *std::max_element(times.begin(), times.end());
  return std::max(largest, ceil_div_nonnegative(sum, stations));
}

int counting_lb2(const std::vector<int> &times, int stations) {
  if (times.empty()) return 0;
  if (stations <= 0) return INF;
  std::vector<int> sorted = times;
  std::sort(sorted.begin(), sorted.end(), std::greater<int>());
  int best = 0;
  const int limit = (static_cast<int>(sorted.size()) - 1) / stations;
  for (int k = 1; k <= limit; ++k) {
    int value = 0;
    for (int i = 0; i <= k; ++i) value += sorted[k * stations - i];
    best = std::max(best, value);
  }
  return best;
}

int lm2_station_bound(const std::vector<int> &times, int cycle) {
  int j1 = 0, j2 = 0;
  for (int t : times) {
    if (2LL * t > cycle)
      ++j1;
    else if (2LL * t == cycle)
      ++j2;
  }
  return j1 + (j2 + 1) / 2;
}

int lm3_station_bound(const std::vector<int> &times, int cycle) {
  int j1 = 0, j2 = 0, j3 = 0, j4 = 0;
  for (int t : times) {
    if (3LL * t > 2LL * cycle)
      ++j1;
    else if (3LL * t == 2LL * cycle)
      ++j2;
    else if (3LL * t > cycle)
      ++j3;
    else if (3LL * t == cycle)
      ++j4;
  }
  const int numerator_sixths = 4 * j2 + 3 * j3 + 2 * j4;
  return j1 + (numerator_sixths + 5) / 6;
}

int l3_station_bound(const std::vector<int> &times, int cycle) {
  int best = 0;
  for (int tbar = 1; tbar <= cycle / 2; ++tbar) {
    int j1 = 0, j2 = 0, j3 = 0;
    long long sum_j2 = 0, sum_j3 = 0, slots_j2 = 0;
    for (int t : times) {
      if (cycle - tbar < t) {
        ++j1;
      } else if (2LL * t > cycle && t <= cycle - tbar) {
        ++j2;
        sum_j2 += t;
        slots_j2 += (cycle - t) / tbar;
      } else if (t >= tbar && 2LL * t <= cycle) {
        ++j3;
        sum_j3 += t;
      }
    }
    const long long residual_capacity = 1LL * cycle * j2 - sum_j2;
    const long long term1 =
        ceil_div_signed(sum_j3 - residual_capacity, cycle);
    const int denominator = cycle / tbar;
    const long long term2 =
        denominator > 0 ? ceil_div_signed(j3 - slots_j2, denominator) : 0;
    const int extra =
        static_cast<int>(std::max({0LL, term1, term2}));
    best = std::max(best, j1 + j2 + extra);
  }
  return best;
}

// Exact integer implementation of LM4.  Delivery times are represented with
// denominator "cycle", so no floating-point rounding enters the bound.
int lm4_station_bound(const Instance &inst, const std::vector<unsigned char> &use,
                      int cycle) {
  std::vector<long long> eta(inst.n, 0);
  for (auto it = inst.topo.rbegin(); it != inst.topo.rend(); ++it) {
    const int i = *it;
    if (!use[i]) continue;
    std::vector<int> jobs;
    for (int j : inst.succ[i])
      if (use[j]) jobs.push_back(j);
    std::sort(jobs.begin(), jobs.end(), [&](int a, int b) {
      if (eta[a] != eta[b]) return eta[a] > eta[b];
      return a < b;
    });
    long long prefix = 0, value = 0;
    for (int j : jobs) {
      prefix += inst.time[j];
      value = std::max(value, prefix + eta[j]);
    }
    eta[i] = value;
    const long long rounded = 1LL * ceil_div_nonnegative(eta[i], cycle) * cycle;
    if (eta[i] + inst.time[i] > rounded) eta[i] = rounded;
  }

  std::vector<int> jobs;
  for (int i = 0; i < inst.n; ++i)
    if (use[i]) jobs.push_back(i);
  std::sort(jobs.begin(), jobs.end(), [&](int a, int b) {
    if (eta[a] != eta[b]) return eta[a] > eta[b];
    return a < b;
  });
  long long prefix = 0, eta0 = 0;
  for (int i : jobs) {
    prefix += inst.time[i];
    eta0 = std::max(eta0, prefix + eta[i]);
  }
  return ceil_div_nonnegative(eta0, cycle);
}

int combined_salbp1_bound(const Instance &inst, const std::vector<int> &tasks,
                          int cycle, bool with_lm4) {
  if (tasks.empty()) return 0;
  std::vector<int> times;
  times.reserve(tasks.size());
  for (int i : tasks) times.push_back(inst.time[i]);
  int result = std::max({lm2_station_bound(times, cycle),
                         lm3_station_bound(times, cycle),
                         l3_station_bound(times, cycle)});
  if (with_lm4) {
    std::vector<unsigned char> use(inst.n, 0);
    for (int i : tasks) use[i] = 1;
    result = std::max(result, lm4_station_bound(inst, use, cycle));
  }
  return result;
}

int first_cycle_accepted(const Instance &inst, const std::vector<int> &task_ids,
                         int stations, int start, int kind) {
  std::vector<int> times;
  times.reserve(task_ids.size());
  for (int i : task_ids) times.push_back(inst.time[i]);
  int c = start;
  for (;;) {
    int b = 0;
    if (kind == 2)
      b = lm2_station_bound(times, c);
    else if (kind == 3)
      b = lm3_station_bound(times, c);
    else if (kind == 4)
      b = l3_station_bound(times, c);
    else {
      std::vector<unsigned char> use(inst.n, 0);
      for (int i : task_ids) use[i] = 1;
      b = lm4_station_bound(inst, use, c);
    }
    if (b <= stations) return c;
    ++c;
  }
}

BoundBreakdown root_bounds(const Instance &inst, bool with_lm4) {
  std::vector<int> ids(inst.n), times = inst.time;
  std::iota(ids.begin(), ids.end(), 0);
  BoundBreakdown b;
  b.lb1 = parallel_lb1(times, inst.m);
  b.lb2 = counting_lb2(times, inst.m);
  const int start = std::max(b.lb1, b.lb2);
  b.lm2 = first_cycle_accepted(inst, ids, inst.m, start, 2);
  b.lm3 = first_cycle_accepted(inst, ids, inst.m, start, 3);
  b.l3 = first_cycle_accepted(inst, ids, inst.m, start, 4);
  b.lm4 = with_lm4 ? first_cycle_accepted(inst, ids, inst.m, start, 5) : 0;
  b.combined = std::max({b.lb1, b.lb2, b.lm2, b.lm3, b.l3, b.lm4});
  return b;
}

struct Solution {
  int cycle = INF;
  std::vector<std::vector<int>> stations;
};

bool better_heuristic_task(const Instance &inst, int a, int b, int rule) {
  if (b < 0) return true;
  auto successor_count = [&](int i) {
    int count = 0;
    for (std::uint64_t word : inst.transitive_succ[i])
      count += __builtin_popcountll(word);
    return count;
  };
  switch (rule) {
    case 0:
      if (inst.positional_weight[a] != inst.positional_weight[b])
        return inst.positional_weight[a] > inst.positional_weight[b];
      break;
    case 1:
      if (inst.time[a] != inst.time[b]) return inst.time[a] > inst.time[b];
      break;
    case 2: {
      const int sa = successor_count(a), sb = successor_count(b);
      if (sa != sb) return sa > sb;
      break;
    }
    case 3:
      if (inst.succ[a].size() != inst.succ[b].size())
        return inst.succ[a].size() > inst.succ[b].size();
      break;
    case 4:
      if (inst.time[a] != inst.time[b]) return inst.time[a] < inst.time[b];
      break;
    default:
      break;
  }
  if (inst.positional_weight[a] != inst.positional_weight[b])
    return inst.positional_weight[a] > inst.positional_weight[b];
  if (inst.time[a] != inst.time[b]) return inst.time[a] > inst.time[b];
  return a < b;
}

std::optional<Solution> constructive_heuristic(const Instance &inst, int cycle,
                                               int rule) {
  std::vector<int> degree(inst.n);
  std::vector<unsigned char> assigned(inst.n, 0);
  for (int i = 0; i < inst.n; ++i)
    degree[i] = static_cast<int>(inst.pred[i].size());
  int assigned_count = 0;
  Solution solution;
  solution.cycle = cycle;

  for (int k = 0; k < inst.m && assigned_count < inst.n; ++k) {
    std::vector<int> station;
    int load = 0;

    if (k == inst.m - 1) {
      int remaining = 0;
      for (int i : inst.topo)
        if (!assigned[i]) remaining += inst.time[i];
      if (remaining <= cycle) {
        for (int i : inst.topo) {
          if (!assigned[i]) {
            station.push_back(i);
            assigned[i] = 1;
            ++assigned_count;
          }
        }
        solution.stations.push_back(std::move(station));
        break;
      }
    }

    for (;;) {
      int best = -1;
      for (int i = 0; i < inst.n; ++i) {
        if (!assigned[i] && degree[i] == 0 && load + inst.time[i] <= cycle &&
            better_heuristic_task(inst, i, best, rule))
          best = i;
      }
      if (best < 0) break;
      station.push_back(best);
      load += inst.time[best];
      assigned[best] = 1;
      ++assigned_count;
      for (int j : inst.succ[best]) --degree[j];
    }
    if (station.empty()) return std::nullopt;
    solution.stations.push_back(std::move(station));
  }
  if (assigned_count != inst.n) return std::nullopt;
  while (static_cast<int>(solution.stations.size()) < inst.m)
    solution.stations.emplace_back();
  return solution;
}

std::optional<Solution> multi_rule_heuristic(const Instance &inst, int cycle) {
  for (int rule = 0; rule <= 4; ++rule) {
    auto solution = constructive_heuristic(inst, cycle, rule);
    if (solution) return solution;
  }
  return std::nullopt;
}

Solution initial_solution(const Instance &inst, int lower_bound) {
  const int formula_ub =
      std::max(inst.max_time, 2 * (inst.total_time / inst.m));
  int previous = lower_bound - 1;
  int candidate = lower_bound;
  int fib_a = 0, fib_b = 1;
  std::optional<Solution> best;

  while (candidate <= formula_ub) {
    auto found = multi_rule_heuristic(inst, candidate);
    if (found) {
      best = std::move(found);
      break;
    }
    previous = candidate;
    const int next_fib = fib_a + fib_b;
    fib_a = fib_b;
    fib_b = next_fib;
    candidate = std::min(formula_ub, lower_bound + fib_b);
    if (candidate <= previous) ++candidate;
  }

  if (!best) {
    for (candidate = std::max(formula_ub + 1, lower_bound);
         candidate <= inst.total_time; ++candidate) {
      auto found = multi_rule_heuristic(inst, candidate);
      if (found) {
        best = std::move(found);
        break;
      }
    }
  }
  if (!best)
    throw std::logic_error("constructive heuristic failed at total task time");

  // Refine only the last Fibonacci interval.  A failed heuristic call never
  // changes the exact lower bound.
  for (int c = std::max(lower_bound, previous + 1); c < best->cycle; ++c) {
    auto found = multi_rule_heuristic(inst, c);
    if (found) best = std::move(found);
  }
  return *best;
}

struct PathNode {
  std::shared_ptr<PathNode> parent;
  std::vector<int> station;
};

std::vector<std::vector<int>> path_to_stations(
    const std::shared_ptr<PathNode> &path, int m) {
  std::vector<std::vector<int>> reversed;
  for (auto p = path; p; p = p->parent) reversed.push_back(p->station);
  std::reverse(reversed.begin(), reversed.end());
  while (static_cast<int>(reversed.size()) < m) reversed.emplace_back();
  return reversed;
}

struct State {
  std::vector<std::int16_t> degree;
  int k = 0;
  int value = 0;
  int assigned_work = 0;
  int assigned_count = 0;
  std::uint64_t version = 0;
  std::uint64_t sequence = 0;
  std::shared_ptr<PathNode> path;
};

struct StatePriority {
  bool operator()(const State &a, const State &b) const {
    const long long idle_a = 1LL * a.k * a.value - a.assigned_work;
    const long long idle_b = 1LL * b.k * b.value - b.assigned_work;
    if (idle_a != idle_b) return idle_a > idle_b;
    if (a.value != b.value) return a.value > b.value;
    if (a.assigned_count != b.assigned_count)
      return a.assigned_count < b.assigned_count;
    return a.sequence > b.sequence;
  }
};

struct Memo {
  int value = INF;
  std::uint64_t version = 0;
  bool processed = false;
};

std::string state_key(const std::vector<std::int16_t> &degree, int k) {
  std::string key;
  key.resize(2 * (degree.size() + 1));
  const std::uint16_t kk = static_cast<std::uint16_t>(k);
  key[0] = static_cast<char>(kk & 0xffU);
  key[1] = static_cast<char>((kk >> 8U) & 0xffU);
  for (std::size_t i = 0; i < degree.size(); ++i) {
    const std::uint16_t value =
        degree[i] < 0 ? 0U : static_cast<std::uint16_t>(degree[i] + 1);
    key[2 + 2 * i] = static_cast<char>(value & 0xffU);
    key[3 + 2 * i] = static_cast<char>((value >> 8U) & 0xffU);
  }
  return key;
}

struct Statistics {
  std::uint64_t expanded_states = 0;
  std::uint64_t generated_loads = 0;
  std::uint64_t stored_states = 0;
  std::uint64_t memory_prunes = 0;
  std::uint64_t maximum_load_prunes = 0;
  std::uint64_t successor_prunes = 0;
  std::uint64_t jackson_prunes = 0;
  std::uint64_t generalized_jackson_prunes = 0;
  std::uint64_t bound_prunes = 0;
};

enum class StopReason { EXHAUSTED, TIME, MEMORY, TRUNCATED };

struct PhaseResult {
  StopReason stop = StopReason::EXHAUSTED;
  int lower_bound = 0;
  bool proved = false;
  bool extension_limit_hit = false;
};

class Solver {
 public:
  Solver(const Instance &instance, const Options &options, int root_lb,
         Solution incumbent, Clock::time_point total_start)
      : inst_(instance),
        opt_(options),
        root_lb_(root_lb),
        incumbent_(std::move(incumbent)),
        start_(total_start),
        deadline_(start_ +
                  std::chrono::duration_cast<Clock::duration>(
                      std::chrono::duration<double>(opt_.time_limit))) {}

  struct Result {
    int lower_bound;
    Solution solution;
    std::string status;
    double seconds;
    std::size_t peak_memory_states;
    Statistics statistics;
    std::string phase;
  };

  Result solve() {
    if (incumbent_.cycle == root_lb_) return make_result(root_lb_, "OPTIMAL", "bounds");

    PhaseResult phase1 = run_phase(opt_.max_extensions);
    if (phase1.proved)
      return make_result(incumbent_.cycle, "OPTIMAL", "limited");
    if (time_expired())
      return make_result(std::max(root_lb_, phase1.lower_bound), "TIME_LIMIT",
                         "limited");

    PhaseResult phase2 = run_phase(0);
    if (phase2.proved)
      return make_result(incumbent_.cycle, "OPTIMAL", "unlimited");

    std::string status = phase2.stop == StopReason::MEMORY ? "MEMORY_LIMIT"
                                                           : "TIME_LIMIT";
    return make_result(std::max(root_lb_, phase2.lower_bound), status,
                       "unlimited");
  }

 private:
  const Instance &inst_;
  const Options &opt_;
  int root_lb_;
  Solution incumbent_;
  Clock::time_point start_;
  Clock::time_point deadline_;
  Statistics total_stats_;
  std::size_t peak_memory_states_ = 0;
  std::uint64_t sequence_ = 0;

  std::vector<std::priority_queue<State, std::vector<State>, StatePriority>>
      queues_;
  std::unordered_map<std::string, Memo> memory_;
  Statistics phase_stats_;
  bool stopped_time_ = false;
  bool stopped_memory_ = false;
  bool extension_limit_hit_ = false;
  std::size_t extension_cap_ = 0;
  int interrupted_parent_lb_ = INF;
  int next_queue_ = 0;

  bool time_expired() const { return Clock::now() >= deadline_; }

  Result make_result(int lb, std::string status, std::string phase) {
    const double seconds =
        std::chrono::duration<double>(Clock::now() - start_).count();
    if (status == "OPTIMAL") lb = incumbent_.cycle;
    return {lb, incumbent_, std::move(status), seconds, peak_memory_states_,
            total_stats_, std::move(phase)};
  }

  std::vector<std::int16_t> root_degree() const {
    std::vector<std::int16_t> degree(inst_.n);
    for (int i = 0; i < inst_.n; ++i) {
      if (inst_.pred[i].size() >
          static_cast<std::size_t>(std::numeric_limits<std::int16_t>::max()))
        throw std::runtime_error("task indegree exceeds state encoding");
      degree[i] = static_cast<std::int16_t>(inst_.pred[i].size());
    }
    return degree;
  }

  PhaseResult run_phase(std::size_t extension_cap) {
    queues_.clear();
    queues_.resize(inst_.m);
    memory_.clear();
    phase_stats_ = {};
    stopped_time_ = false;
    stopped_memory_ = false;
    extension_limit_hit_ = false;
    extension_cap_ = extension_cap;
    interrupted_parent_lb_ = INF;
    next_queue_ = 0;

    State root;
    root.degree = root_degree();
    root.value = root_lb_;
    root.sequence = sequence_++;
    const std::string root_key = state_key(root.degree, 0);
    memory_.emplace(root_key, Memo{root_lb_, 1, false});
    root.version = 1;
    queues_[0].push(std::move(root));

    State state;
    while (!stopped_time_ && !stopped_memory_ && pop_next(state)) {
      if (time_expired()) {
        stopped_time_ = true;
        interrupted_parent_lb_ = std::min(interrupted_parent_lb_, state.value);
        break;
      }
      const std::string key = state_key(state.degree, state.k);
      auto memo_it = memory_.find(key);
      if (memo_it == memory_.end() || memo_it->second.version != state.version ||
          memo_it->second.processed || memo_it->second.value != state.value)
        continue;
      memo_it->second.processed = true;
      if (state.value >= incumbent_.cycle) continue;
      ++phase_stats_.expanded_states;
      enumerate_state(state);
    }

    peak_memory_states_ = std::max(peak_memory_states_, memory_.size());
    accumulate_stats();

    PhaseResult result;
    result.extension_limit_hit = extension_limit_hit_;
    if (stopped_time_)
      result.stop = StopReason::TIME;
    else if (stopped_memory_)
      result.stop = StopReason::MEMORY;
    else if (extension_limit_hit_)
      result.stop = StopReason::TRUNCATED;
    else
      result.stop = StopReason::EXHAUSTED;

    const bool any_open = has_valid_open_state();
    result.proved =
        !stopped_time_ && !stopped_memory_ && !extension_limit_hit_ && !any_open;
    if (result.proved) {
      result.lower_bound = incumbent_.cycle;
    } else if (extension_limit_hit_) {
      // The truncated phase omitted branches; its frontier cannot safely
      // improve the global lower bound.
      result.lower_bound = root_lb_;
    } else {
      result.lower_bound = frontier_lower_bound();
    }
    return result;
  }

  void accumulate_stats() {
    total_stats_.expanded_states += phase_stats_.expanded_states;
    total_stats_.generated_loads += phase_stats_.generated_loads;
    total_stats_.stored_states += phase_stats_.stored_states;
    total_stats_.memory_prunes += phase_stats_.memory_prunes;
    total_stats_.maximum_load_prunes += phase_stats_.maximum_load_prunes;
    total_stats_.successor_prunes += phase_stats_.successor_prunes;
    total_stats_.jackson_prunes += phase_stats_.jackson_prunes;
    total_stats_.generalized_jackson_prunes +=
        phase_stats_.generalized_jackson_prunes;
    total_stats_.bound_prunes += phase_stats_.bound_prunes;
  }

  bool state_is_current(const State &state) const {
    const auto it = memory_.find(state_key(state.degree, state.k));
    return it != memory_.end() && it->second.version == state.version &&
           !it->second.processed && it->second.value == state.value;
  }

  bool pop_next(State &state) {
    if (queues_.empty()) return false;
    for (int attempt = 0; attempt < inst_.m; ++attempt) {
      const int k = (next_queue_ + attempt) % inst_.m;
      auto &queue = queues_[k];
      while (!queue.empty() && !state_is_current(queue.top())) queue.pop();
      if (!queue.empty()) {
        state = queue.top();
        queue.pop();
        next_queue_ = (k + 1) % inst_.m;
        return true;
      }
    }
    return false;
  }

  bool has_valid_open_state() const {
    for (auto queue : queues_) {
      while (!queue.empty()) {
        if (state_is_current(queue.top())) return true;
        queue.pop();
      }
    }
    return false;
  }

  int frontier_lower_bound() const {
    int lb = interrupted_parent_lb_;
    for (auto queue : queues_) {
      while (!queue.empty()) {
        if (state_is_current(queue.top())) lb = std::min(lb, queue.top().value);
        queue.pop();
      }
    }
    if (lb == INF) lb = root_lb_;
    return std::max(root_lb_, std::min(lb, incumbent_.cycle));
  }

  bool solitary_task(const State &state, int &task) const {
    int smallest = -1, largest_available = -1;
    for (int i = 0; i < inst_.n; ++i) {
      if (state.degree[i] < 0) continue;
      if (smallest < 0 || inst_.time[i] < inst_.time[smallest] ||
          (inst_.time[i] == inst_.time[smallest] && i < smallest))
        smallest = i;
      if (state.degree[i] == 0 &&
          (largest_available < 0 ||
           inst_.time[i] > inst_.time[largest_available] ||
           (inst_.time[i] == inst_.time[largest_available] &&
            i < largest_available)))
        largest_available = i;
    }
    if (smallest < 0 || largest_available < 0) return false;
    if (inst_.time[smallest] + inst_.time[largest_available] >=
        incumbent_.cycle) {
      task = largest_available;
      return true;
    }
    return false;
  }

  void assign_task(std::vector<std::int16_t> &degree, int task) const {
    if (degree[task] != 0) throw std::logic_error("assigning unavailable task");
    degree[task] = -1;
    for (int j : inst_.succ[task]) {
      if (degree[j] <= 0)
        throw std::logic_error("inconsistent predecessor count while assigning");
      --degree[j];
    }
  }

  void unassign_task(std::vector<std::int16_t> &degree, int task) const {
    for (int j : inst_.succ[task]) {
      if (degree[j] < 0) continue;
      ++degree[j];
    }
    degree[task] = 0;
  }

  void enumerate_state(const State &state) {
    int solitary = -1;
    if (opt_.dominance_rules && solitary_task(state, solitary)) {
      std::vector<std::int16_t> degree = state.degree;
      assign_task(degree, solitary);
      std::vector<int> station{solitary};
      evaluate_child(state, degree, station, inst_.time[solitary], true);
      return;
    }

    std::vector<std::int16_t> degree = state.degree;
    std::vector<int> eligible;
    for (int i : inst_.topo)
      if (degree[i] == 0) eligible.push_back(i);
    std::vector<int> station;
    std::size_t generated_for_state = 0;
    enumerate_station(state, degree, eligible, 0, station, 0,
                      generated_for_state);
  }

  void enumerate_station(const State &state,
                         std::vector<std::int16_t> &degree,
                         const std::vector<int> &eligible, std::size_t start,
                         std::vector<int> &station, int load,
                         std::size_t &generated_for_state) {
    if (stopped_time_ || stopped_memory_) return;
    if ((phase_stats_.generated_loads & 1023ULL) == 0 && time_expired()) {
      stopped_time_ = true;
      interrupted_parent_lb_ = std::min(interrupted_parent_lb_, state.value);
      return;
    }

    if (!station.empty()) {
      bool maximal_for_local_bound = true;
      if (load < state.value) {
        for (int i = 0; i < inst_.n; ++i) {
          if (degree[i] == 0 && load + inst_.time[i] <= state.value) {
            maximal_for_local_bound = false;
            break;
          }
        }
      }
      if (load >= state.value || maximal_for_local_bound) {
        if (extension_cap_ > 0 && generated_for_state >= extension_cap_) {
          extension_limit_hit_ = true;
          return;
        }
        ++generated_for_state;
        ++phase_stats_.generated_loads;
        evaluate_child(state, degree, station, load, false);
        if (stopped_time_ || stopped_memory_) return;
      } else {
        ++phase_stats_.maximum_load_prunes;
      }
    }

    for (std::size_t pos = start; pos < eligible.size(); ++pos) {
      const int task = eligible[pos];
      if (degree[task] != 0 || load + inst_.time[task] >= incumbent_.cycle)
        continue;
      std::vector<int> sub_eligible = eligible;
      assign_task(degree, task);
      for (int j : inst_.succ[task]) {
        if (degree[j] == 0) sub_eligible.push_back(j);
      }
      station.push_back(task);
      enumerate_station(state, degree, sub_eligible, pos + 1, station,
                        load + inst_.time[task], generated_for_state);
      station.pop_back();
      unassign_task(degree, task);
      if (stopped_time_ || stopped_memory_) return;
      if (extension_cap_ > 0 && generated_for_state >= extension_cap_) {
        extension_limit_hit_ = true;
        return;
      }
    }
  }

  bool successor_rule(const std::vector<std::int16_t> &degree,
                      const std::vector<int> &station) const {
    bool station_has_successor = false;
    for (int i : station)
      if (!inst_.succ[i].empty()) {
        station_has_successor = true;
        break;
      }
    if (station_has_successor) return false;
    for (int i = 0; i < inst_.n; ++i)
      if (degree[i] >= 0 && !inst_.succ[i].empty()) return true;
    return false;
  }

  bool jackson_rule(const State &parent,
                    const std::vector<std::int16_t> &degree,
                    const std::vector<int> &station, int load) const {
    const int old_cycle = std::max(parent.value, load);
    for (int dominant = 0; dominant < inst_.n; ++dominant) {
      if (degree[dominant] != 0) continue;
      for (int task : station) {
        if (!inst_.dominates[dominant][task]) continue;
        const int swapped_load =
            load - inst_.time[task] + inst_.time[dominant];
        if (std::max(parent.value, swapped_load) == old_cycle) return true;
      }
    }
    return false;
  }

  std::vector<int> remaining_tasks(
      const std::vector<std::int16_t> &degree) const {
    std::vector<int> ids;
    for (int i = 0; i < inst_.n; ++i)
      if (degree[i] >= 0) ids.push_back(i);
    return ids;
  }

  int child_bound(const State &parent,
                  const std::vector<std::int16_t> &degree, int load,
                  int child_k) const {
    const std::vector<int> ids = remaining_tasks(degree);
    if (ids.empty()) return std::max(parent.value, load);
    const int stations = inst_.m - child_k;
    if (stations <= 0) return INF;
    std::vector<int> times;
    times.reserve(ids.size());
    for (int i : ids) times.push_back(inst_.time[i]);
    int c = std::max({parent.value, load, parallel_lb1(times, stations),
                      counting_lb2(times, stations)});
    while (c < incumbent_.cycle &&
           combined_salbp1_bound(inst_, ids, c, opt_.lm4_search) > stations)
      ++c;
    return c;
  }

  std::vector<std::int16_t> degrees_from_assigned(
      const std::vector<unsigned char> &assigned) const {
    std::vector<std::int16_t> degree(inst_.n, 0);
    for (int i = 0; i < inst_.n; ++i) {
      if (assigned[i]) {
        for (int p : inst_.pred[i])
          if (!assigned[p]) return {};
        degree[i] = -1;
      } else {
        int count = 0;
        for (int p : inst_.pred[i])
          if (!assigned[p]) ++count;
        degree[i] = static_cast<std::int16_t>(count);
      }
    }
    return degree;
  }

  bool generalized_jackson_rule(
      const std::vector<std::int16_t> &degree,
      const std::vector<int> &station, int child_k, int value) const {
    if (!opt_.generalized_jackson) return false;
    std::vector<unsigned char> assigned(inst_.n, 0);
    for (int i = 0; i < inst_.n; ++i) assigned[i] = degree[i] < 0;
    for (int task : station) {
      for (int dominant = 0; dominant < inst_.n; ++dominant) {
        if (assigned[dominant] || !inst_.dominates[dominant][task]) continue;
        assigned[task] = 0;
        assigned[dominant] = 1;
        const auto swapped_degree = degrees_from_assigned(assigned);
        assigned[dominant] = 0;
        assigned[task] = 1;
        if (swapped_degree.empty()) continue;
        const auto it = memory_.find(state_key(swapped_degree, child_k));
        if (it != memory_.end() && it->second.value <= value) return true;
      }
    }
    return false;
  }

  void evaluate_child(const State &parent,
                      const std::vector<std::int16_t> &degree,
                      const std::vector<int> &station, int load,
                      bool from_solitary) {
    if (load >= incumbent_.cycle) return;
    if (!from_solitary && opt_.dominance_rules) {
      if (successor_rule(degree, station)) {
        ++phase_stats_.successor_prunes;
        return;
      }
      if (jackson_rule(parent, degree, station, load)) {
        ++phase_stats_.jackson_prunes;
        return;
      }
    }

    int remaining_count = 0;
    for (auto d : degree)
      if (d >= 0) ++remaining_count;
    const int child_k = parent.k + 1;
    const int cycle = std::max(parent.value, load);
    auto path = std::make_shared<PathNode>(
        PathNode{parent.path, std::vector<int>(station)});

    if (remaining_count == 0) {
      if (cycle < incumbent_.cycle) {
        incumbent_.cycle = cycle;
        incumbent_.stations = path_to_stations(path, inst_.m);
      }
      return;
    }
    if (child_k >= inst_.m) {
      ++phase_stats_.bound_prunes;
      return;
    }

    const int value = child_bound(parent, degree, load, child_k);
    if (value >= incumbent_.cycle) {
      ++phase_stats_.bound_prunes;
      return;
    }

    const std::string key = state_key(degree, child_k);
    auto it = memory_.find(key);
    if (it != memory_.end() && it->second.value <= value) {
      ++phase_stats_.memory_prunes;
      return;
    }
    if (generalized_jackson_rule(degree, station, child_k, value)) {
      ++phase_stats_.generalized_jackson_prunes;
      return;
    }

    std::uint64_t version = 1;
    if (it == memory_.end()) {
      if (memory_.size() >= opt_.memory_states) {
        stopped_memory_ = true;
        interrupted_parent_lb_ = std::min(interrupted_parent_lb_, parent.value);
        return;
      }
      auto inserted = memory_.emplace(key, Memo{value, 1, false});
      it = inserted.first;
      ++phase_stats_.stored_states;
    } else {
      version = it->second.version + 1;
      it->second = Memo{value, version, false};
    }
    version = it->second.version;
    peak_memory_states_ = std::max(peak_memory_states_, memory_.size());

    State child;
    child.degree = degree;
    child.k = child_k;
    child.value = value;
    child.assigned_work = parent.assigned_work + load;
    child.assigned_count = parent.assigned_count +
                           static_cast<int>(station.size());
    child.version = version;
    child.sequence = sequence_++;
    child.path = std::move(path);
    queues_[child_k].push(std::move(child));
  }
};

bool validate_solution(const Instance &inst, const Solution &solution,
                       std::string &error) {
  if (static_cast<int>(solution.stations.size()) != inst.m) {
    error = "solution does not contain exactly m station slots";
    return false;
  }
  std::vector<int> station_of(inst.n, -1);
  int observed_cycle = 0;
  for (int k = 0; k < inst.m; ++k) {
    int load = 0;
    for (int i : solution.stations[k]) {
      if (i < 0 || i >= inst.n) {
        error = "solution contains an invalid task identifier";
        return false;
      }
      if (station_of[i] >= 0) {
        error = "task " + std::to_string(i + 1) + " is assigned twice";
        return false;
      }
      station_of[i] = k;
      load += inst.time[i];
    }
    observed_cycle = std::max(observed_cycle, load);
  }
  for (int i = 0; i < inst.n; ++i) {
    if (station_of[i] < 0) {
      error = "task " + std::to_string(i + 1) + " is unassigned";
      return false;
    }
    for (int j : inst.succ[i]) {
      if (station_of[i] > station_of[j]) {
        error = "precedence relation " + std::to_string(i + 1) + "," +
                std::to_string(j + 1) + " is violated";
        return false;
      }
    }
  }
  if (observed_cycle != solution.cycle) {
    error = "reported cycle time differs from the station loads";
    return false;
  }
  return true;
}

void write_solution(const std::string &file, const Instance &inst,
                    const Solver::Result &result) {
  std::ofstream out(file);
  if (!out) throw std::runtime_error("cannot write solution file: " + file);
  out << "status " << result.status << "\n";
  out << "lower_bound " << result.lower_bound << "\n";
  out << "upper_bound " << result.solution.cycle << "\n";
  for (int k = 0; k < inst.m; ++k) {
    int load = 0;
    out << "station " << (k + 1) << ":";
    for (int i : result.solution.stations[k]) {
      out << ' ' << (i + 1);
      load += inst.time[i];
    }
    out << " | load " << load << "\n";
  }
}

bool file_is_empty(const std::string &file) {
  std::ifstream in(file, std::ios::binary | std::ios::ate);
  return !in || in.tellg() == 0;
}

std::string csv_escape(const std::string &s) {
  if (s.find_first_of(",\"\n") == std::string::npos) return s;
  std::string result = "\"";
  for (char c : s) {
    if (c == '"') result += '"';
    result += c;
  }
  result += '"';
  return result;
}

void append_csv(const std::string &file, const Instance &inst,
                const Solver::Result &result, const Options &opt) {
  const bool header = file_is_empty(file);
  std::ofstream out(file, std::ios::app);
  if (!out) throw std::runtime_error("cannot append result CSV: " + file);
  if (header) {
    out << "instance,n,m,status,LB,UB,gap_percent,time_seconds,phase,threads,"
           "time_limit_seconds,memory_state_limit,max_extensions,"
           "dominance_rules,generalized_jackson,lm4_root,lm4_search,"
           "peak_memory_states,expanded_states,generated_loads,stored_states,"
           "memory_prunes,maximum_load_prunes,successor_prunes,jackson_prunes,"
           "generalized_jackson_prunes,bound_prunes\n";
  }
  const double gap = result.solution.cycle > 0
                         ? 100.0 * (result.solution.cycle - result.lower_bound) /
                               result.solution.cycle
                         : 0.0;
  const auto &s = result.statistics;
  const std::string stable_name =
      std::filesystem::path(inst.name).stem().string();
  out << csv_escape(stable_name) << ',' << inst.n << ',' << inst.m << ','
      << result.status << ',' << result.lower_bound << ','
      << result.solution.cycle << ',' << std::fixed << std::setprecision(6)
      << gap << ',' << result.seconds << ',' << result.phase << ",1,"
      << opt.time_limit << ',' << opt.memory_states << ',' << opt.max_extensions
      << ',' << (opt.dominance_rules ? 1 : 0) << ','
      << (opt.generalized_jackson ? 1 : 0) << ',' << (opt.lm4_root ? 1 : 0)
      << ',' << (opt.lm4_search ? 1 : 0) << ','
      << result.peak_memory_states << ',' << s.expanded_states << ','
      << s.generated_loads << ',' << s.stored_states << ',' << s.memory_prunes
      << ',' << s.maximum_load_prunes << ',' << s.successor_prunes << ','
      << s.jackson_prunes << ',' << s.generalized_jackson_prunes << ','
      << s.bound_prunes << '\n';
}

void print_help(const char *program) {
  std::cout
      << "Usage: " << program << " INSTANCE [options]\n\n"
      << "Direct branch, bound and remember solver for SALBP-2.\n\n"
      << "Options:\n"
      << "  --stations M             station count (required for .IN2)\n"
      << "  --time-limit SECONDS     total wall-clock limit (default: 600)\n"
      << "  --memory-states N        remembered-state limit (default: 60000000)\n"
      << "  --max-extensions N       phase-1 loads per state (default: 10000)\n"
      << "  --no-generalized-jackson disable generalized Jackson dominance\n"
      << "  --no-dominance           disable logical dominance rules\n"
      << "  --no-lm4-root            omit LM4 from the root lower bound\n"
      << "  --lm4-search             also use LM4 at search states\n"
      << "  --csv-output FILE        append one machine-readable result row\n"
      << "  --solution-output FILE   write the incumbent station assignment\n"
      << "  --quiet                  suppress progress/detail output\n"
      << "  --help                   show this help\n";
}

Options parse_options(int argc, char **argv) {
  Options opt;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto require_value = [&](const std::string &name) -> std::string {
      if (i + 1 >= argc) throw std::runtime_error("missing value for " + name);
      return argv[++i];
    };
    if (arg == "--help" || arg == "-h") {
      print_help(argv[0]);
      std::exit(0);
    } else if (arg == "--stations") {
      opt.stations = std::stoi(require_value(arg));
    } else if (arg == "--time-limit") {
      opt.time_limit = std::stod(require_value(arg));
    } else if (arg == "--memory-states") {
      opt.memory_states = std::stoull(require_value(arg));
    } else if (arg == "--max-extensions") {
      opt.max_extensions = std::stoull(require_value(arg));
    } else if (arg == "--no-generalized-jackson") {
      opt.generalized_jackson = false;
    } else if (arg == "--no-dominance") {
      opt.dominance_rules = false;
      opt.generalized_jackson = false;
    } else if (arg == "--no-lm4-root") {
      opt.lm4_root = false;
    } else if (arg == "--lm4-search") {
      opt.lm4_search = true;
    } else if (arg == "--csv-output") {
      opt.csv_output = require_value(arg);
    } else if (arg == "--solution-output") {
      opt.solution_output = require_value(arg);
    } else if (arg == "--quiet") {
      opt.quiet = true;
    } else if (!arg.empty() && arg[0] == '-') {
      throw std::runtime_error("unknown option: " + arg);
    } else if (opt.input.empty()) {
      opt.input = arg;
    } else {
      throw std::runtime_error("multiple input files supplied");
    }
  }
  if (opt.input.empty()) throw std::runtime_error("no input instance supplied");
  if (opt.time_limit <= 0) throw std::runtime_error("time limit must be positive");
  if (opt.memory_states == 0)
    throw std::runtime_error("memory-state limit must be positive");
  return opt;
}

}  // namespace direct_bbr

int main(int argc, char **argv) {
  using namespace direct_bbr;
  try {
    const auto total_start = Clock::now();
    const Options opt = parse_options(argc, argv);
    const Instance inst = read_instance(opt);
    const BoundBreakdown bounds = root_bounds(inst, opt.lm4_root);
    Solution initial = initial_solution(inst, bounds.combined);

    if (!opt.quiet) {
      std::cout << "INSTANCE file=" << inst.name << " n=" << inst.n
                << " m=" << inst.m << " total_time=" << inst.total_time << '\n';
      std::cout << "ROOT_BOUNDS LB1=" << bounds.lb1 << " LB2=" << bounds.lb2
                << " LM2=" << bounds.lm2 << " LM3=" << bounds.lm3
                << " L3=" << bounds.l3 << " LM4=" << bounds.lm4
                << " combined=" << bounds.combined << '\n';
      std::cout << "INITIAL_SOLUTION UB=" << initial.cycle << '\n';
    }

    Solver solver(inst, opt, bounds.combined, std::move(initial), total_start);
    Solver::Result result = solver.solve();
    std::string validation_error;
    if (!validate_solution(inst, result.solution, validation_error))
      throw std::logic_error("internal solution validation failed: " +
                             validation_error);
    if (result.lower_bound > result.solution.cycle)
      throw std::logic_error("internal bound invariant LB <= UB failed");

    const double gap =
        100.0 * (result.solution.cycle - result.lower_bound) /
        result.solution.cycle;
    std::cout << "RESULT status=" << result.status
              << " LB=" << result.lower_bound
              << " UB=" << result.solution.cycle << " gap_percent="
              << std::fixed << std::setprecision(6) << gap
              << " time_seconds=" << result.seconds
              << " phase=" << result.phase
              << " memory_states=" << result.peak_memory_states << '\n';
    if (!opt.quiet) {
      const auto &s = result.statistics;
      std::cout << "SEARCH expanded=" << s.expanded_states
                << " generated_loads=" << s.generated_loads
                << " stored=" << s.stored_states
                << " memory_prunes=" << s.memory_prunes
                << " max_load_prunes=" << s.maximum_load_prunes
                << " successor_prunes=" << s.successor_prunes
                << " jackson_prunes=" << s.jackson_prunes
                << " generalized_jackson_prunes="
                << s.generalized_jackson_prunes
                << " bound_prunes=" << s.bound_prunes << '\n';
    }
    if (!opt.solution_output.empty())
      write_solution(opt.solution_output, inst, result);
    if (!opt.csv_output.empty()) append_csv(opt.csv_output, inst, result, opt);
    return result.status == "OPTIMAL" ? 0 : 2;
  } catch (const std::exception &e) {
    std::cerr << "ERROR: " << e.what() << '\n';
    return 1;
  }
}
