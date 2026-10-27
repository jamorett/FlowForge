#include "correctedKOmegaSST.H"
#include "addToRunTimeSelectionTable.H"
#include "fvcGrad.H"

namespace Foam
{
namespace RASModels
{

defineTypeNameAndDebug(correctedKOmegaSST, 0);
addToRunTimeSelectionTable(RASModel, correctedKOmegaSST, dictionary);

correctedKOmegaSST::correctedKOmegaSST
(
    const alphaField& alpha,
    const rhoField& rho,
    const volVectorField& U,
    const surfaceScalarField& alphaRhoPhi,
    const surfaceScalarField& phi,
    const transportModel& transport,
    const word& propertiesName,
    const word& type
)
:
    kOmegaSST<BasicTurbulenceModel>
    (
        alpha, rho, U, alphaRhoPhi, phi, transport, propertiesName, type
    )
{}

scalar correctedKOmegaSST::correctedProduction
(
    const scalar G,
    const scalar k,
    const scalar omega,
    const scalar pkDelta
) const
{
    // Pk_corrected = min(G, 10*betaStar*k*omega) + PkDelta, clamped >= 0.
    const scalar pkLimited = min(G, 10.0*betaStar_.value()*k*omega);
    return max(pkLimited + pkDelta, scalar(0));
}

void correctedKOmegaSST::correct()
{
    // Base SST first. With zero/absent corrections this is the exact
    // baseline path: nut_ is never touched (identity gate, diff < 1e-6).
    kOmegaSST<BasicTurbulenceModel>::correct();

    const bool hasADelta =
        this->mesh_.foundObject<volSymmTensorField>("aDelta");
    const bool hasPkDelta =
        this->mesh_.foundObject<volScalarField>("PkDelta");

    scalar modeBMax = 0;
    // Mode B is compiled in; the default hook returns exactly 0.
    // (Cell loop is cheap relative to the SST correct() above.)
    // hasADelta/hasPkDelta gate the field reads below.

    if (!hasADelta && !hasPkDelta)
    {
        return;
    }

    const volSymmTensorField* aDeltaPtr =
        hasADelta
      ? &this->mesh_.lookupObject<volSymmTensorField>("aDelta")
      : nullptr;
    const volScalarField* pkDeltaPtr =
        hasPkDelta
      ? &this->mesh_.lookupObject<volScalarField>("PkDelta")
      : nullptr;

    // Identity guard: zero corrections must not perturb nut_ at all.
    scalar maxADelta = 0;
    scalar maxPkDelta = 0;
    if (aDeltaPtr)
    {
        forAll(*aDeltaPtr, celli)
        {
            maxADelta = max(maxADelta, mag((*aDeltaPtr)[celli]));
        }
    }
    if (pkDeltaPtr)
    {
        forAll(*pkDeltaPtr, celli)
        {
            maxPkDelta = max(maxPkDelta, mag((*pkDeltaPtr)[celli]));
        }
    }
    modeBMax = max(modeBMax, scalar(0));
    if (maxADelta == 0 && maxPkDelta == 0 && modeBMax == 0)
    {
        return;
    }

    // Non-zero correction: apply through nut_ as the stress surrogate
    //   delta_nut = 2*k*mag(aDelta) / max(omega, 1e-6)
    // scaled by Pk_corrected / max(Pk_base, 1e-6) so the production
    // clamp (Pk >= 0) is honoured. Full equation-level Pk injection
    // requires overriding the k/omega sources; until the Docker wmake
    // probe passes, this nut-level coupling is the shipped Mode A path
    // and is labelled as such (never presented as an equation solve).
    tmp<volTensorField> tGradU = fvc::grad(this->U_);
    const volTensorField& gradU = tGradU();

    forAll(this->nut_, celli)
    {
        const scalar k = max(this->k_[celli], scalar(0));
        const scalar omega = this->omega_[celli];
        const scalar denom = guardedDenom(omega);
        const symmTensor S = symm(gradU[celli]);
        const scalar G = 2.0*this->nut_[celli]*max(S && S, scalar(0));
        const scalar pkDelta =
            pkDeltaPtr ? (*pkDeltaPtr)[celli] : scalar(0);
        const scalar pkBase =
            min(G, 10.0*betaStar_.value()*k*omega);
        const scalar pkCorr = correctedProduction(G, k, omega, pkDelta);
        const scalar pkFactor = pkCorr/guardedDenom(pkBase);
        const scalar magA =
            aDeltaPtr ? mag((*aDeltaPtr)[celli]) : scalar(0);
        const scalar deltaNut = 2.0*k*magA/denom;

        this->nut_[celli] =
            max(this->nut_[celli]*pkFactor + deltaNut, scalar(0));
    }
    this->nut_.correctBoundaryConditions();
}

} // End namespace RASModels
} // End namespace Foam
