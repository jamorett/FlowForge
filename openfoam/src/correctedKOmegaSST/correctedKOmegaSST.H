/*---------------------------------------------------------------------------*\
  correctedKOmegaSST: k-omega SST + anisotropy/production corrections (S2.1).

  tau_corrected = tau_SST + 2*k*aDelta
  Pk_corrected  = min(G, 10*betaStar*k*omega) + PkDelta, clamped >= 0
  Every denominator is guarded with max(denom, 1e-6).

  Mode A (fixed field): reads aDelta (volSymmTensorField) and PkDelta
  (volScalarField) from the time directory. Zero fields => exact identity
  with baseline SST (correct() returns after the base call, nut untouched).
  Mode B (compiled): code generated per candidate is inserted at the
  GENERATED_MODE_B marker in correctedKOmegaSST.C and compiled in.

  Template over the turbulence-model family like every official RAS
  model; concrete registration for incompressible flow happens at the
  bottom of correctedKOmegaSST.C via makeRASModel.
\*---------------------------------------------------------------------------*/
#ifndef correctedKOmegaSST_H
#define correctedKOmegaSST_H

#include "dimensionedScalar.H"
#include "volFields.H"
#include "turbulenceModel.H"
#include "fvMatrices.H"
#include "fvc.H"
#include "fvm.H"
#include "kOmegaSST.H"

namespace Foam
{
namespace RASModels
{

/*---------------------------------------------------------------------------*\
                      Class correctedKOmegaSST Declaration
\*---------------------------------------------------------------------------*/

template<class BasicTurbulenceModel>
class correctedKOmegaSST
:
    public kOmegaSST<BasicTurbulenceModel>
{
public:

    typedef typename BasicTurbulenceModel::alphaField alphaField;
    typedef typename BasicTurbulenceModel::rhoField rhoField;
    typedef typename BasicTurbulenceModel::transportModel transportModel;


    //- Runtime type information
    TypeName("correctedKOmegaSST");


protected:

    //- Fixed-field corrections (Mode A). Nobody else constructs these
    //  fields, so the registry never holds them: they must be read here
    //  at start time and kept frozen for the run (oracle semantics).
    autoPtr<volSymmTensorField> aDelta_;
    autoPtr<volScalarField> PkDelta_;

    //- Explicit Reynolds-stress correction (SpaRTA form): 2k*aDelta,
    //  rebuilt from the current k every correct() and injected through
    //  divDevTau. The nut path alone is a scalar surrogate that cannot
    //  carry the tensorial redistribution (measured: 5e-5 response on a
    //  0.5-magnitude correction); this term is the real correction.
    autoPtr<volSymmTensorField> tauDelta_;

    //- Pk with limiter + correction, clamped >= 0. Denominator-free.
    scalar correctedProduction
    (
        const scalar G,
        const scalar k,
        const scalar omega,
        const scalar pkDelta
    ) const;

    //- Guarded denominator: max(denom, 1e-6)
    static scalar guardedDenom(const scalar denom)
    {
        return max(denom, scalar(1e-6));
    }

    //- Mode B hook. Generated code overrides the return value per cell;
    //  the shipped default is exactly zero (no correction).
    virtual scalar modeBCorrection(const label celli) const
    {
        // GENERATED_MODE_B: SymPy-generated expression is compiled here.
        return scalar(0);
    }


public:

    correctedKOmegaSST
    (
        const alphaField& alpha,
        const rhoField& rho,
        const volVectorField& U,
        const surfaceScalarField& alphaRhoPhi,
        const surfaceScalarField& phi,
        const transportModel& transport,
        const word& propertiesName = turbulenceModel::propertiesName,
        const word& type = typeName
    );

    virtual ~correctedKOmegaSST() = default;

    virtual void correct();

    //- Momentum stress with the explicit correction subtracted:
    //  divDevReff_base - div(2k*aDelta) (SpaRTA: tau = tau_SST + 2k*aDelta).
    //  divDevReff is the v2512 incompressible entry point simpleFoam
    //  assembles the momentum equation with.
    virtual tmp<fvVectorMatrix> divDevReff(volVectorField& U) const;
};


} // End namespace RASModels
} // End namespace Foam

#endif
