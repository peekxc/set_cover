#include <vector>
#include <functional>
#include <numeric>
#include <algorithm>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

using namespace pybind11::literals;
namespace py = pybind11;

// Counter to avoid storing the set difference 
struct Counter {
  struct value_type { template<typename T> value_type(const T&) { } };
  void push_back(const value_type&) noexcept { ++count; }
  size_t count = 0;
};

template< typename Iter1, typename Iter2 >
size_t setdiff_size(Iter1 b1, const Iter1 e1, Iter2 b2, const Iter2 e2) noexcept {
  Counter c;
  std::set_difference(b1, e1, b2, e2, std::back_inserter(c));
  return c.count;
}

using std::begin;
using std::end; 
using std::vector; 
py::array_t< int > greedy_set_cover(py::array_t< int >& indices, py::array_t< int >& indptr, py::array_t<double>& weights, const size_t n){
  const size_t J = weights.size();

  auto I = indptr.unchecked<1>();
  auto ind = vector< int >(indices.size()); 
  for (size_t i = 0; i < ind.size(); ++i){
    ind[i] = I[i];
  }
  auto IP = indptr.unchecked<1>();
  auto W = weights.unchecked<1>();

  // Point indices in the current cover (initialized to empty set)
  auto pci = vector< int >();
  pci.reserve(n);

  // Candidate sets to choose from
  auto cand_sets = vector< int >(J);
  std::iota(cand_sets.begin(), cand_sets.end(), 0);

  // Priorities on the set of candidate sets
  auto set_imports = vector< double >();
  set_imports.reserve(n);
  
  // Actual indices of the sets making up the solution
  auto soln = vector< int >();

  size_t cc = 0; 
  while(pci.size() < n || cc < n){
    
    // Main computational set: get the sizes of the all the set differences
    set_imports.clear();
    for (size_t ji = 0; ji < cand_sets.size(); ++ji){
      size_t j = cand_sets[ji]; // absolute column / set index 
      auto jb = ind.begin()+IP[j];
      auto je = ind.begin()+IP[j+1];
      const size_t I_sz = setdiff_size(jb, je, pci.begin(), pci.end());
      set_imports.push_back(I_sz == 0 ? std::numeric_limits<double>::infinity() : W[j]/I_sz);
    }
    
    // Greedy step
    auto min_it = std::min_element(set_imports.begin(), set_imports.end());
    auto min_ind = std::distance(set_imports.begin(), min_it);
    const size_t best_j = cand_sets[min_ind]; // absolute column index
    // cand_sets.erase(cand_sets.begin()+best_j); // remove the set from future consideration
    cand_sets.erase(std::remove(cand_sets.begin(), cand_sets.end(), best_j), cand_sets.end());

    // Union the best set into the point cover
    auto jb = ind.begin()+IP[best_j];
    auto je = ind.begin()+IP[best_j+1];

    const size_t c_sz = pci.size();
    std::set_difference(jb, je, pci.begin(), pci.end(), std::back_inserter(pci));
    // if (set_imports[best_j] == std::numeric_limits< double >::max()){
    //   // set difference empty
    //   soln.push_back(best_j);
    // } else {
    // Merge the set into the set of point indices
    const size_t j_sz = std::distance(jb, je); // static_cast< size_t >(set_imports[best_j]*W[best_j]);
    std::inplace_merge(pci.begin(), pci.begin() + c_sz, pci.end()); 
    // auto last = std::unique(pci.begin(), pci.end());
    // pci.erase(last, pci.end());
    soln.push_back(best_j);
    // }
    cc++; 
  }

  py::array_t< int > soln_np(soln.size(), soln.data());
  return(soln_np);
}

PYBIND11_MODULE(_cover, m) {
  m.def("greedy_set_cover", &greedy_set_cover);
};