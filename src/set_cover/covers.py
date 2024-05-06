from math import comb
import numpy as np
from typing import Callable, Union
from numpy.typing import ArrayLike
from scipy.sparse import csr_matrix, csc_matrix, coo_matrix, find, csc_array, csr_array, coo_array
from scipy.spatial.distance import pdist, cdist, squareform
from combin import inverse_choose
from .loaders import _clean_sp_mat

## Predicates to simplify type-checking
def is_distance_matrix(x: ArrayLike) -> bool:
	''' Checks whether 'x' is a distance matrix, i.e. is square, symmetric, and that the diagonal is all 0. '''
	x = np.array(x, copy=False)
	is_square = x.ndim == 2	and (x.shape[0] == x.shape[1])
	return(False if not(is_square) else np.all(np.diag(x) == 0))

def is_pairwise_distances(x: ArrayLike) -> bool:
	''' Checks whether 'x' is a 1-d array of pairwise distances '''
	x = np.array(x, copy=False) # don't use asanyarray here
	if x.ndim > 1: return(False)
	n = inverse_choose(len(x), 2)
	return(x.ndim == 1 and len(x) == comb(n, 2))

def is_point_cloud(x: ArrayLike) -> bool: 
	''' Checks whether 'x' is a 2-d array of points '''
	return(isinstance(x, np.ndarray) and x.ndim == 2)

## Classical MDS 
def cmds(G: ArrayLike, d: int = 2, coords: bool = True):
	'''Generates a d-dimensional a gram matrix 'G' onto  embedding via Classical (Torgerson's) Multi-Dimensional Scaling (CMDS)

	CMDS is a linear dimensionality reduction algorithm that projects a double-centered symmetric inner product (gram) matrix 'G' to a 
	lower dimensional space whose coordinates minimize the reconstruction error of centered scalar products, or 'strain'.

	CMDS is dual to PCA in the sense that the d-dimensional covariance-derived projection produced by PCA minimizes the 
	same inner-product-derived 'strain' objective minimized by CMDS. 

	Parameters: 
		G = set of pairwise inner products or a squared Euclidean distance matrix. 
		d = dimension of the embedding to produce.
		center = whether to center the data prior to computing eigenvectors
		coords = whether to return the embedding (default = True), or just return the eigenvectors
	
	Returns:
		if coords = True, returns the projection of 'X' onto the largest 'd' eigenvectors of X's covariance matrix. Otherwise, 
		the eigenvalues and eigenvectors can be returned as-is. 
	''' 
	is_pd = is_pairwise_distances(G)
	is_dm = is_distance_matrix(G)
	assert is_pd or is_dm, "Input 'D' should set of pairwise distances or distance matrix"
	G = squareform(G) if is_pd else G
	n = G.shape[0]
	G_center = G.mean(axis=0)
	G = -0.50 * (G  - G_center - G_center.reshape((n,1)) + G_center.mean())
	evals, evecs = np.linalg.eigh(G)
	evals, evecs = evals[(n-d):n], evecs[:,(n-d):n]

	# Compute the coordinates using positive-eigenvalued components only     
	if coords:               
		w = np.flip(np.maximum(evals, np.repeat(0.0, d)))
		Y = np.fliplr(evecs) @ np.diag(np.sqrt(w))
		return(Y)
	else: 
		w = np.where(evals > 0)[0]
		ni = np.setdiff1d(np.arange(d), w)
		evecs[:,ni] = 1.0
		evals[ni] = 0.0
		return(evals, evecs)

def pca(X: ArrayLike, d: int = 2, center: bool = False, coords: bool = True) -> ArrayLike:
	''' 
	Projects 'X' onto a d-dimensional embedding via Principal Component Analysis (PCA)

	PCA is a linear dimensionality reduction algorithm that projects a point set 'X' onto a lower dimensional space 
	using an orthogonal projector built from the eigenvalue decomposition of its covariance matrix. 

	PCA is dual to CMDS in the sense that the d-dimensional embedding produced by CMDS on the gram matrix  
	of squared Euclidean distances from 'X' satisfies the same reconstruction as the d-dimensional projection of 'X' with PCA. 

	Parameters: 
		X = (n x D) point cloud / design matrix of n points in D dimensions. 
		d = dimension of the embedding to produce.
		center = whether to center the data prior to computing eigenvectors
		coords = whether to return the embedding (default), or just return the eigenvectors
	
	Returns:
		if coords = True (default), returns the projection of 'X' onto the largest 'd' eigenvectors of X's covariance matrix. 
		Otherwise, the eigenvalues and eigenvectors can be returned as-is. 
	'''
	X = np.atleast_2d(X)
	assert is_point_cloud(X), "Input should be a point cloud, not a distance matrix."
	if center: 
		X -= X.mean(axis = 0)
	evals, evecs = np.linalg.eigh(np.cov(X, rowvar=False))
	idx = np.argsort(evals)[::-1] # descending order to pick the largest components first 
	if coords:
		return(np.dot(X, evecs[:,idx[range(d)]]))
	else: 
		return(evals[idx[range(d)]], evecs[:,idx[range(d)]])

def neighborhood_graph(X: np.ndarray, r: float, ind = None):
	"""Constructs an 'r'-neighborhood graph on the point cloud 'X' at the given indices 'ind'
		
	Returns: 
		G = compressed (n x i) adjacency list, where n = |X| and i = |ind|, given as a CSR sparse matrix 
		r = radius of the ball to thicken each point in X with
	"""
	ind = np.array(range(X.shape[0])) if ind is None else ind
	m = len(ind)
	r,c,v = find(cdist(X, X[ind,:]) <= r*2)
	G = coo_matrix((v, (r,c)), shape=(X.shape[0], m), dtype=bool)
	return G.tocsc()

def tangent_bundle(M: csr_array, X: np.ndarray, d: int = 2, centers: np.ndarray = None) -> dict:
	"""Estimates the tangent bundle of 'M' via local PCA on neighborhoods in 'X'

	This function estimates the d-dimensional tangent spaces of neighborhoods in 'X' given by columns in 'M'.
	
	Parameters: 
		M = Adjacency list, given as a sparse CSR matrix
		X = coordinates of the vertices of 'G'
		d = dimension of the tangent space
		centers = points to center the tangent space estimates. If None, each neighborhoods is centered around its average. 
	"""
	# assert isinstance(M, csr_matrix) or isinstance(M, csr_array), "Adjacency must be a CSR matrix."
	if centers is not None:
		centers = np.atleast_2d(centers)
		assert centers.shape[1] == X.shape[1], "Centers must have same dimension as 'X'"
		assert len(centers) == M.shape[1], "Number of centers doesn't match number of neighborhoods in 'M'"
	M = _clean_sp_mat(M)
	D = X.shape[1]
	m = M.shape[1]
	tangents = [None] * m 
	for j, ind in enumerate(np.split(M.indices, M.indptr)[1:-1]):
		
		## First compute the base point
		center = centers[j] if centers is not None else X[ind,:].mean(axis=0)
		if len(ind) == 0: 
			# raise ValueError("Singularity at point {i}: neighborhood too small to compute tangent")
			tangents[j] = (center, np.eye(D, d))
			continue 
		
		## Get tangent space estimates at centered points
		centered_pts = X[ind,:] - center
		_, T_y = pca(centered_pts, d=d, coords=False)
		tangents[j] = (center, T_y) # ambient x local, columns represent unit vectors
	return tangents

## TODO: add various tangent-related weight functions 
## 1. (avg/min/max) distance to tangent plane
## 2. (avg/min/max) cosine similarity (between what? )
## 3. span / Point-to-point cosine similarity 
## 4. Stiefel canonical metric / angles between orthogonal spaces
## 5. Alignment of normals? 
def bundle_weights(M, TM, method: str, reduce: Union[str, Callable], X: ArrayLike = None):
	"""Computes a geometrically informative statistic on each tangent space the tangent bundle.
	
	This function computes variety
	Assumes the connectivity of the tangent space vectors is given by M
	"""
	A = M.tocoo()
	assert method in ['distance', 'cosine', 'angle']
	stat_f = getattr(np, reduce) if isinstance(reduce, str) else reduce
	assert isinstance(stat_f, Callable), "Reduce function should be the name of a numpy aggregate function or a Callable itself."
	base_points = np.array([p for p,v in TM]) # n x D
	tangent_vec = np.array([v.T.flatten() for p,v in TM]) # n x D x d

	if method == 'cosine':
		cosine_dist_sgn = lambda j: np.min(cdist(tangent_vec[[j,j]] * np.array([[1],[-1]]), tangent_vec[A.row[A.col == j]], 'cosine'), axis=0)
		cosine_dist = [cosine_dist_sgn(j) for j in range(M.shape[1])]
		weights = np.array([stat_f(cd) for cd in cosine_dist])
		return weights 
	elif method == 'distance':
		weights = np.zeros(len(TM), dtype=np.float32)
		for j, (pt, T_y) in enumerate(TM):
			neighbor_ind = A.row[A.col == j]
			neighbor_coords = base_points[neighbor_ind]
			
			## Collect dist to each tangent line 
			proj_dist = np.zeros(shape=(len(neighbor_ind), T_y.shape[1]))
			for ii, tangent_v in enumerate(T_y.T):
				tangent_inner_prod = (neighbor_coords - pt).dot(tangent_v)
				proj_coords = pt + tangent_v * tangent_inner_prod[:,np.newaxis]
				proj_dist[:,ii] = np.linalg.norm(proj_coords - neighbor_coords, axis=1)
			weights[j] = stat_f(proj_dist)
			return weights
	else:
		raise ValueError("Invlaid method {method} supplied")



def tangent_neighbor_graph(X: ArrayLike, d: int, r: float, ind = None):
	''' 
	Constructs an r-neighborhood graph on the point cloud 'X' at the given indices 'ind', and then computes an orthogonal basis 
	which approximates the d-dimensional tangent space around each of those points. 

	Parameters: 
		X = (n x d) point cloud data in Euclidean space, or and (n x n) sparse adjacency matrix yielding a weighted neighborhood graph
		d = local dimension where the metric is approximately Euclidean
		r = radius around each point determining the neighborhood from which to compute the tangent vector
		ind = indices to approximate the neighborhoods at. If not specified, will use every point. 

	Returns: 
		G = the neighborhood graph, given as an (n x len(ind)) incidence matrix
		weights = len(ind)-length array 
	'''
	ind = np.array(range(X.shape[0])) if ind is None else ind
	m = len(ind)
	r,c,v = find(cdist(X, X[ind,:]) <= r*2)
	weights, tangents = np.zeros(m), [None]*m
	for i, x in enumerate(X[ind,:]): 
		nn_idx = c[r == i] #np.append(np.flatnonzero(G[i,:].A), i)
		if len(nn_idx) < 2: 
			# raise ValueError("Singularity at point {i}: neighborhood too small to compute tangent")
			weights[i] = np.inf 
			tangents[i] = np.eye(X.shape[1], d)
			continue 
		
		## Get tangent space estimates at centered points
		centered_pts = X[nn_idx,:]-x
		_, T_y = pca(centered_pts, d=d, coords=False)
		tangents[i] = T_y # ambient x local

		## Project all points onto tangent plane, then measure distance between projected points and original
		proj_coords = np.dot(centered_pts, T_y) # project points onto d-tangent plane
		proj_points = np.array([np.sum(p*T_y, axis=1) for p in proj_coords]) # orthogonal projection in D dimensions
		weights[i] = np.sum([np.sqrt(np.sum(diff**2)) for diff in (centered_pts - proj_points)]) # np.linalg.norm(centered_pts - proj_points)
	
	#assert np.all(G.A == G.A.T)
	G = coo_matrix((v, (r,c)), shape=(X.shape[0], len(ind)), dtype=bool)
	return(G.tocsc(), weights, tangents)
	#return(weights, tangents)



def valid_cover(A, ind: np.ndarray = None) -> bool:
	"""Determines whether certain subsets of a set of subsets forms a covers every row."""
	import sortednp
	n, J = A.shape
	A = csc_array(A).astype(bool) if not hasattr(A, "indices") else A
	A.eliminate_zeros()
	A.sort_indices()
	subset_splits = np.split(A.indices, A.indptr)[1:-1]
	assert len(subset_splits) == J, "Splitting of cover array failed. Are there empty columns?"
	if ind is not None:
		ind = np.array(ind).astype(int) 
		subset_splits = [subset_splits[i] for i in ind]
	covered_ind = sortednp.kway_merge(*subset_splits, assume_sorted=True, duplicates=4)
	return len(covered_ind) == n