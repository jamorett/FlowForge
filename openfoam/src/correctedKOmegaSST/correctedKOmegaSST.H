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
\*---------------------------------------------------------------------------*/
#ifndef correctedKOmegaSST_H
#define correctedKOmegaSST_H

#include "kOmegaSST.H"

namespace Foam
{
namespace RASModels
{

class correctedKOmegaSST
:
    public kOmegaSST<BasicTurbulenceModel>
{
protected:

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

    TypeName("correctedKOmegaSST");

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
};

} // End namespace RASModels
} // End namespace Foam

#endif
